/**
 * three.js scene for the Champions playoff bracket (plain three, no react-three-fiber).
 *
 * One class owns the renderer, scene, controls and every GPU resource, and `dispose()`
 * releases all of it. React only mounts/unmounts it (see Bracket3D.tsx).
 *
 * "heavy" (desktop, fine pointer, >=1024px): bloom post-processing, thousands of GPU particles,
 *   animated grid + dust field, depth fog, DPR up to 2.
 * "light" (phones/tablets): DPR <= 1.5, a few hundred particles, no composer / bloom.
 *
 * Flow semantics: the only team-specific flows are the two sides of each verified Upper
 * Quarterfinal along the (projected) winner edge, scaled by model p_win. Every other edge is a
 * dashed, dim "projected" path with no team on it. Nothing here marks a team as advanced.
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { feedLabel, type BracketEdge, type BracketGraph, type BracketNode, type FlowSide } from "../../lib/bracketGraph";
import { utcShort } from "../../lib/format";
import type { BracketLayout } from "./layout";

export type Quality = "heavy" | "light";
export type ThemeName = "dark" | "light";

/** Screen-space anchors (px, relative to the canvas): node top-centre and its right/left mid-edges. */
export interface PickInfo { id: number; x: number; y: number; rx: number; lx: number; my: number }
export interface CameraState { position: [number, number, number]; target: [number, number, number] }

export interface EngineOptions {
  container: HTMLElement;
  graph: BracketGraph;
  layout: BracketLayout;
  quality: Quality;
  theme: ThemeName;
  reducedMotion: boolean;
  /** Start at the home view without the fly-in (theme switches, re-mounts). */
  initialCamera?: CameraState | null;
  onHover: (p: PickInfo | null) => void;
  onSelect: (p: PickInfo | null) => void;
  onLost: () => void;
}

interface Palette {
  bg: string; surface: string; surface3: string; line: string; lineStrong: string;
  text: string; text2: string; text3: string; accent: string; accent2: string;
  plate: string; plateDark: string; display: string; mono: string;
}

function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string, fb: string) => cs.getPropertyValue(n).trim() || fb;
  return {
    bg: v("--bg", "#07090A"), surface: v("--surface-2", "#161B18"), surface3: v("--surface-3", "#1E2421"),
    line: v("--line", "#2A322D"), lineStrong: v("--line-strong", "#333D37"),
    text: v("--text", "#E6ECE7"), text2: v("--text-2", "#B9C3BC"), text3: v("--text-3", "#8A948D"),
    accent: v("--model", "#C8F25C"), accent2: v("--model-2", "#7E9440"),
    plate: v("--logo-plate", "#1A201C"), plateDark: v("--logo-plate-dark", "#C9D1CB"),
    display: v("--font-display", "'Chakra Petch', system-ui, sans-serif"),
    mono: v("--font-num", "'JetBrains Mono', ui-monospace, monospace"),
  };
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
const clamp01 = (t: number) => Math.min(1, Math.max(0, t));

const FOV = 38;
const FACE_W = 512;
const FACE_H = 256;

/* ---------------------------------------------------------------- shaders */

const PATH_VERT = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const PATH_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;
uniform float uDash;
uniform float uLen;
uniform float uTime;
uniform float uPulse;
uniform float uPhase;
varying vec2 vUv;
void main() {
  float u = vUv.x;
  if (uDash > 0.5) {
    float d = fract(u * uLen / 0.8 - uTime * 0.12);
    if (d > 0.58) discard;
  }
  float pulse = uPulse * pow(max(0.0, sin((u - uTime * 0.14 - uPhase) * 6.28318 * 2.0)), 10.0);
  vec3 col = uColor * (1.0 + pulse * 2.6);
  gl_FragColor = vec4(col, clamp(uOpacity * (0.75 + pulse), 0.0, 1.0));
  #include <colorspace_fragment>
}`;

const PARTICLE_VERT = /* glsl */ `
attribute float aPhase;
attribute vec4 aRand;
uniform vec3 uP0; uniform vec3 uP1; uniform vec3 uP2; uniform vec3 uP3;
uniform vec3 uSide;
uniform float uTime; uniform float uSpeed; uniform float uSize; uniform float uScale; uniform float uSpread;
varying float vAlpha;
void main() {
  float t = fract(aPhase + uTime * uSpeed * (0.85 + aRand.x * 0.3));
  float s = 1.0 - t;
  vec3 pos = s*s*s*uP0 + 3.0*s*s*t*uP1 + 3.0*s*t*t*uP2 + t*t*t*uP3;
  float swell = sin(3.14159 * t);
  pos += uSide * (aRand.y - 0.5) * uSpread * (0.25 + swell);
  pos.z += (aRand.z - 0.5) * uSpread * (0.25 + swell);
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * (0.55 + aRand.w) * uScale / max(0.1, -mv.z);
  vAlpha = smoothstep(0.0, 0.09, t) * smoothstep(1.0, 0.88, t);
}`;

const PARTICLE_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uIntensity;
varying float vAlpha;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d);
  gl_FragColor = vec4(uColor * (0.6 + a), a * a * vAlpha * uIntensity);
  #include <colorspace_fragment>
}`;

const DUST_VERT = /* glsl */ `
attribute vec4 aRand;
uniform float uTime; uniform float uScale; uniform float uSize;
varying float vAlpha;
void main() {
  vec3 p = position;
  p.y += sin(uTime * 0.18 + aRand.x * 40.0) * 0.9;
  p.x += cos(uTime * 0.12 + aRand.y * 40.0) * 0.9;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * (0.4 + aRand.z) * uScale / max(0.1, -mv.z);
  vAlpha = (0.25 + 0.75 * aRand.w) * (0.6 + 0.4 * sin(uTime * 0.6 + aRand.x * 30.0));
}`;

const DUST_FRAG = /* glsl */ `
uniform vec3 uColor; uniform float uOpacity;
varying float vAlpha;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.1, d);
  gl_FragColor = vec4(uColor, a * vAlpha * uOpacity);
  #include <colorspace_fragment>
}`;

const GRID_VERT = /* glsl */ `
varying vec2 vPlane;
void main() {
  vPlane = position.xy;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const GRID_FRAG = /* glsl */ `
uniform vec3 uColor; uniform float uTime; uniform float uOpacity; uniform float uRadius; uniform float uMove;
varying vec2 vPlane;
void main() {
  vec2 c = vPlane / 4.0;
  vec2 g = abs(fract(c - 0.5) - 0.5) / max(fwidth(c), vec2(1e-4));
  float line = 1.0 - min(min(g.x, g.y), 1.0);
  float r = length(vPlane);
  float fade = smoothstep(uRadius, uRadius * 0.15, r);
  float ring = exp(-pow((r - fract(uTime * 0.045) * uRadius) / 5.0, 2.0)) * uMove;
  float a = line * (0.10 + ring * 0.7) * fade * uOpacity;
  if (a < 0.003) discard;
  gl_FragColor = vec4(uColor, a);
  #include <colorspace_fragment>
}`;

const GLOW_VERT = /* glsl */ `
varying vec2 vP;
void main() { vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;

const GLOW_FRAG = /* glsl */ `
uniform vec3 uColor; uniform float uStrength; uniform vec2 uHalf;
varying vec2 vP;
void main() {
  vec2 q = abs(vP) - uHalf;
  float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
  float a = exp(-max(d, 0.0) * 2.4) * uStrength;
  if (a < 0.004) discard;
  gl_FragColor = vec4(uColor, a);
  #include <colorspace_fragment>
}`;

/* ---------------------------------------------------------------- helpers */

interface Lane {
  edge: BracketEdge;
  curve: THREE.CubicBezierCurve3;
  flow: FlowSide | null;
  points: THREE.Points | null;
  token: THREE.Group | null;
  tokenPhase: number;
  mat: THREE.ShaderMaterial;
  pMat: THREE.ShaderMaterial | null;
  size: number;
}

interface NodeView {
  node: BracketNode;
  group: THREE.Group;
  body: THREE.Mesh;
  frame: THREE.Line;
  frameMat: THREE.LineBasicMaterial | THREE.LineDashedMaterial;
  glow: THREE.Mesh;
  glowMat: THREE.ShaderMaterial;
  hover: number;
  delay: number;
}

function loadLogoTexture(loader: THREE.TextureLoader, src: string, renderer: THREE.WebGLRenderer): Promise<{ tex: THREE.Texture; dark: boolean } | null> {
  return new Promise(resolve => {
    loader.load(src, tex => {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
      tex.generateMipmaps = true;
      let dark = false;
      try {
        const img = tex.image as CanvasImageSource & { naturalWidth?: number; naturalHeight?: number };
        const c = document.createElement("canvas");
        c.width = c.height = 32;
        const ctx = c.getContext("2d");
        if (ctx) {
          ctx.drawImage(img, 0, 0, 32, 32);
          const d = ctx.getImageData(0, 0, 32, 32).data;
          let n = 0, nb = 0;
          for (let i = 0; i < d.length; i += 4) {
            if (d[i + 3] < 16) continue;
            n++;
            if ((0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255 < 0.15) nb++;
          }
          dark = n > 0 && nb / n > 0.5;
        }
      } catch { /* tainted/odd image: keep the normal plate */ }
      resolve({ tex, dark });
    }, undefined, () => resolve(null));
  });
}

function textSprite(text: string, color: string, font: string, px: number): THREE.Sprite {
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d")!;
  ctx.font = `700 ${px}px ${font}`;
  const w = Math.ceil(ctx.measureText(text).width) + 16;
  c.width = w; c.height = Math.ceil(px * 1.5);
  const g = c.getContext("2d")!;
  g.font = `700 ${px}px ${font}`;
  g.textBaseline = "middle";
  g.fillStyle = color;
  g.fillText(text, 8, c.height / 2);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
  const s = new THREE.Sprite(mat);
  const h = 0.9;
  s.scale.set((h * c.width) / c.height, h, 1);
  s.center.set(0, 0.5);
  return s;
}

/* ---------------------------------------------------------------- engine */

export class BracketEngine {
  private o: EngineOptions;
  private pal: Palette;
  private heavy: boolean;
  private light: boolean; // light THEME (not light quality)
  private renderer: THREE.WebGLRenderer;
  private composer: EffectComposer | null = null;
  private bloom: UnrealBloomPass | null = null;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private raycaster = new THREE.Raycaster();
  private canvas: HTMLCanvasElement;
  private nodes: NodeView[] = [];
  private lanes: Lane[] = [];
  private timeUniforms: { value: number }[] = [];
  private scaleUniforms: { value: number }[] = [];
  private disposables: { dispose(): void }[] = [];
  private textures: THREE.Texture[] = [];
  private raf = 0;
  private last = 0;
  private time = 0;
  private ro: ResizeObserver;
  private io: IntersectionObserver | null = null;
  private visible = true;
  private disposed = false;
  private dirty = true;

  private homeTarget = new THREE.Vector3();
  private homeOffset = new THREE.Vector3();
  private homeDist = 30;
  private introT = 0;
  private introDur = 2.6;
  private intro = false;
  private introFrom = new THREE.Vector3();
  private introFromTarget = new THREE.Vector3();
  private reset: { t: number; fromPos: THREE.Vector3; fromTarget: THREE.Vector3 } | null = null;
  private userMoved = false;

  private hovered: NodeView | null = null;
  private selected: NodeView | null = null;
  private lastSel = { x: -999, y: -999 };
  private down: { x: number; y: number; t: number } | null = null;
  private pointerNdc = new THREE.Vector2();
  private pointerDirty = false;
  private pointerType = "";
  private interactive = true;
  private ac = new AbortController();

  constructor(options: EngineOptions) {
    this.o = options;
    this.pal = readPalette();
    this.heavy = options.quality === "heavy";
    this.light = options.theme === "light";

    const { container } = options;
    const w = Math.max(1, container.clientWidth), h = Math.max(1, container.clientHeight);

    this.renderer = new THREE.WebGLRenderer({
      antialias: this.heavy && !this.useBloom(), alpha: false,
      powerPreference: this.heavy ? "high-performance" : "default",
    });
    const dpr = Math.min(window.devicePixelRatio || 1, this.heavy ? 2 : 1.5);
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.renderer.setClearColor(new THREE.Color(this.pal.bg), 1);
    this.canvas = this.renderer.domElement;
    this.canvas.className = "b3d-canvas";
    container.appendChild(this.canvas);
    this.canvas.addEventListener("webglcontextlost", this.onContextLost as EventListener, { signal: this.ac.signal });

    this.scene.background = new THREE.Color(this.pal.bg);
    this.camera = new THREE.PerspectiveCamera(FOV, w / h, 0.1, 600);

    this.computeHome(w / h);
    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true;
    this.controls.minPolarAngle = 0.35;
    this.controls.maxPolarAngle = 1.9;
    this.controls.minAzimuthAngle = -1.5;
    this.controls.maxAzimuthAngle = 1.5;
    this.controls.rotateSpeed = 0.7;
    this.controls.zoomSpeed = 0.8;
    this.applyDistanceLimits();

    this.scene.fog = new THREE.Fog(new THREE.Color(this.pal.bg), this.homeDist * 1.1, this.homeDist * (this.heavy ? 3.4 : 5));

    this.buildEnvironment();
    this.buildNodes();
    this.buildEdges();
    this.buildLabels();
    this.setupComposer(w, h);

    // camera start
    const cam = options.initialCamera;
    if (cam) {
      this.camera.position.set(...cam.position);
      this.controls.target.set(...cam.target);
      this.userMoved = true;
    } else if (!options.reducedMotion) {
      this.startIntro();
    } else {
      this.camera.position.copy(this.homeTarget).add(this.homeOffset);
      this.controls.target.copy(this.homeTarget);
    }
    this.controls.update();

    const sig = { signal: this.ac.signal };
    this.canvas.addEventListener("pointermove", this.onPointerMove, sig);
    this.canvas.addEventListener("pointerdown", this.onPointerDown, sig);
    this.canvas.addEventListener("pointerup", this.onPointerUp, sig);
    this.canvas.addEventListener("pointerleave", this.onPointerLeave, sig);
    this.controls.addEventListener("start", this.onControlStart);
    this.controls.addEventListener("change", this.markDirty);

    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(container);
    if (typeof IntersectionObserver !== "undefined") {
      this.io = new IntersectionObserver(es => { this.visible = es.some(e => e.isIntersecting); if (this.visible) this.markDirty(); });
      this.io.observe(container);
    }
    document.addEventListener("visibilitychange", this.markDirty, sig);

    this.loadLogos();
    this.raf = requestAnimationFrame(this.frame);
  }

  /* ------------------------------------------------------------ public */

  get domElement() { return this.canvas; }

  setInteractive(on: boolean) {
    this.interactive = on;
    this.controls.enabled = on;
    this.canvas.style.touchAction = on ? "none" : "pan-y";
    if (!on) this.hover(null);
  }

  resetView() {
    this.intro = false;
    this.reset = { t: 0, fromPos: this.camera.position.clone(), fromTarget: this.controls.target.clone() };
    this.userMoved = false;
    this.select(null);
    this.markDirty();
  }

  getCameraState(): CameraState {
    const p = this.camera.position, t = this.controls.target;
    return { position: [p.x, p.y, p.z], target: [t.x, t.y, t.z] };
  }

  /** Programmatic selection (keyboard / list tap). */
  selectById(id: number | null) {
    this.select(id == null ? null : this.nodes.find(n => n.node.id === id) ?? null);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ac.abort();
    this.ro.disconnect();
    this.io?.disconnect();
    this.controls.removeEventListener("start", this.onControlStart);
    this.controls.removeEventListener("change", this.markDirty);
    this.controls.dispose();
    this.scene.traverse(obj => {
      const m = obj as THREE.Mesh;
      m.geometry?.dispose?.();
      const mat = m.material as THREE.Material | THREE.Material[] | undefined;
      for (const x of Array.isArray(mat) ? mat : mat ? [mat] : []) {
        for (const v of Object.values(x as unknown as Record<string, unknown>)) if (v instanceof THREE.Texture) v.dispose();
        x.dispose();
      }
    });
    for (const t of this.textures) t.dispose();
    for (const d of this.disposables) d.dispose();
    this.composer?.dispose();
    this.bloom?.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.canvas.remove();
    this.scene.clear();
  }

  /* ------------------------------------------------------------ setup */

  private useBloom() { return this.heavy && !this.light; }

  private setupComposer(w: number, h: number) {
    if (!this.useBloom()) return;
    const rt = new THREE.WebGLRenderTarget(w, h, { type: THREE.HalfFloatType, samples: 4 });
    this.composer = new EffectComposer(this.renderer, rt);
    this.composer.setPixelRatio(this.renderer.getPixelRatio());
    this.composer.setSize(w, h);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(w, h), 0.95, 0.65, 0.62);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
  }

  private computeHome(aspect: number) {
    const { home, orientation } = this.o.layout;
    const bw = home.maxX - home.minX, bh = home.maxY - home.minY;
    const tanH = Math.tan((FOV * Math.PI) / 360);
    const dist = Math.max(bh / 2 / tanH, bw / 2 / (tanH * aspect)) * 1.12 + 3;
    this.homeDist = dist;
    this.homeTarget.set((home.minX + home.maxX) / 2, (home.minY + home.maxY) / 2, -3);
    const phi = orientation === "tall" ? 1.46 : 1.36, theta = orientation === "tall" ? 0.08 : 0.2;
    this.homeOffset.setFromSphericalCoords(dist, phi, theta);
  }

  private applyDistanceLimits() {
    this.controls.minDistance = this.homeDist * 0.28;
    this.controls.maxDistance = this.homeDist * 2.1;
  }

  private startIntro() {
    this.intro = true;
    this.introT = 0;
    this.introFrom.copy(this.homeTarget).add(new THREE.Vector3().setFromSphericalCoords(this.homeDist * 2.2, 0.75, -0.95));
    this.introFromTarget.copy(this.homeTarget);
    this.camera.position.copy(this.introFrom);
    this.controls.target.copy(this.homeTarget);
  }

  private buildEnvironment() {
    const { layout } = this.o;
    const accent = new THREE.Color(this.pal.accent);
    const scale = { value: 1 };
    this.scaleUniforms.push(scale);
    const timeU = { value: 0 };
    this.timeUniforms.push(timeU);
    const blending = this.light ? THREE.NormalBlending : THREE.AdditiveBlending;

    // grid: floor under a wide bracket, back wall behind a tall one
    const o = layout.overview;
    const cx = (o.minX + o.maxX) / 2, cy = (o.minY + o.maxY) / 2;
    const gridMat = new THREE.ShaderMaterial({
      vertexShader: GRID_VERT, fragmentShader: GRID_FRAG, transparent: true, depthWrite: false, blending,
      uniforms: {
        uColor: { value: this.light ? new THREE.Color(this.pal.text3) : accent.clone().multiplyScalar(1.0) },
        uTime: timeU, uOpacity: { value: this.light ? 1.6 : 1 }, uRadius: { value: 110 },
        uMove: { value: this.heavy ? 1 : 0.4 },
      },
    });
    const grid = new THREE.Mesh(new THREE.PlaneGeometry(240, 240), gridMat);
    if (layout.orientation === "wide") {
      grid.rotation.x = -Math.PI / 2;
      grid.position.set(cx, o.minY - 7, -18);
    } else {
      grid.position.set(cx, cy, -34);
    }
    grid.renderOrder = -2;
    this.scene.add(grid);

    // dust
    const n = this.heavy ? 2600 : 420;
    const pos = new Float32Array(n * 3), rnd = new Float32Array(n * 4);
    const spanX = (o.maxX - o.minX) * 1.4 + 20, spanY = (o.maxY - o.minY) * 1.3 + 20;
    for (let i = 0; i < n; i++) {
      pos[i * 3] = cx + (Math.random() - 0.5) * spanX;
      pos[i * 3 + 1] = cy + (Math.random() - 0.5) * spanY;
      pos[i * 3 + 2] = -40 + Math.random() * 56;
      for (let k = 0; k < 4; k++) rnd[i * 4 + k] = Math.random();
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aRand", new THREE.BufferAttribute(rnd, 4));
    const dust = new THREE.Points(geo, new THREE.ShaderMaterial({
      vertexShader: DUST_VERT, fragmentShader: DUST_FRAG, transparent: true, depthWrite: false, blending,
      uniforms: {
        uColor: { value: new THREE.Color(this.light ? this.pal.text3 : this.pal.text2) },
        uOpacity: { value: this.light ? 0.5 : 0.75 }, uTime: timeU, uScale: scale, uSize: { value: this.heavy ? 5.5 : 6.5 },
      },
    }));
    dust.frustumCulled = false;
    this.scene.add(dust);
  }

  private makeFace(node: BracketNode): THREE.CanvasTexture {
    const q = this.heavy ? 1.5 : 1;
    const c = document.createElement("canvas");
    c.width = FACE_W * q; c.height = FACE_H * q;
    const g = c.getContext("2d")!;
    g.scale(q, q);
    const p = this.pal;
    const verified = node.verified && node.match;
    g.fillStyle = p.surface; g.fillRect(0, 0, FACE_W, FACE_H);
    const grad = g.createLinearGradient(0, 0, 0, FACE_H);
    grad.addColorStop(0, "rgba(255,255,255,0.05)"); grad.addColorStop(1, "rgba(0,0,0,0.12)");
    g.fillStyle = grad; g.fillRect(0, 0, FACE_W, FACE_H);
    // header strip
    g.fillStyle = p.surface3; g.fillRect(0, 0, FACE_W, 48);
    g.textBaseline = "middle";
    g.font = `700 24px ${p.display}`;
    g.fillStyle = verified ? p.accent : p.text3;
    g.textAlign = "left";
    g.fillText(`${node.code}${node.bestOf ? ` \u00B7 BO${node.bestOf}` : ""}`, 16, 25);
    g.font = `500 19px ${p.mono}`;
    g.fillStyle = p.text2; g.textAlign = "right";
    g.fillText(node.start ? utcShort(node.start).replace(/ UTC$/, "Z") : "TBD", FACE_W - 16, 26);
    g.textAlign = "left";

    if (verified && node.match) {
      const [a, b] = node.match.sides;
      const aFav = (a.p_win ?? 0) > (b.p_win ?? 0), bFav = (b.p_win ?? 0) > (a.p_win ?? 0);
      [[a, aFav, 48], [b, bFav, 152]].forEach(([s, fav, y0]) => {
        const side = s as typeof a; const top = y0 as number;
        const mid = top + 52;
        g.fillStyle = p.text; g.font = `700 46px ${p.display}`; g.textAlign = "left";
        g.fillText((side.tag ?? side.name).toUpperCase().slice(0, 6), 116, mid - 2);
        g.font = `500 17px ${p.mono}`; g.fillStyle = p.text3;
        g.fillText(side.name.length > 20 ? `${side.name.slice(0, 19)}\u2026` : side.name, 116, mid + 30);
        g.textAlign = "right";
        g.font = `800 50px ${p.mono}`;
        g.fillStyle = fav ? p.accent : p.text3;
        g.fillText(side.p_win != null ? (side.p_win * 100).toFixed(1) : "--.-", FACE_W - 16, mid + 2);
        g.textAlign = "left";
      });
      g.fillStyle = p.line; g.fillRect(14, 150, FACE_W - 28, 2);
    } else {
      g.textAlign = "center";
      g.fillStyle = p.text3;
      const [f0, f1] = node.feeds;
      g.font = `700 34px ${p.display}`;
      g.fillText(f0 ? feedLabel(f0) : "TBD", FACE_W / 2, 100);
      g.font = `500 20px ${p.mono}`; g.fillStyle = p.text3;
      g.fillText("vs", FACE_W / 2, 140);
      g.font = `700 34px ${p.display}`; g.fillStyle = p.text3;
      g.fillText(f1 ? feedLabel(f1) : "TBD", FACE_W / 2, 184);
      g.font = `500 17px ${p.mono}`; g.fillStyle = p.text3;
      g.fillText("TEAMS TBD \u00B7 PROJECTED ROUTE", FACE_W / 2, 230);
    }
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy());
    return tex;
  }

  private buildNodes() {
    const { layout, graph } = this.o;
    const w = layout.nodeW, h = layout.nodeH;
    const accent = new THREE.Color(this.pal.accent);
    const bodyGeo = new THREE.BoxGeometry(w, h, 0.22);
    this.disposables.push(bodyGeo);
    const edgeGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-w / 2, -h / 2, 0.12), new THREE.Vector3(w / 2, -h / 2, 0.12),
      new THREE.Vector3(w / 2, h / 2, 0.12), new THREE.Vector3(-w / 2, h / 2, 0.12), new THREE.Vector3(-w / 2, -h / 2, 0.12),
    ]);
    this.disposables.push(edgeGeo);
    const glowGeo = new THREE.PlaneGeometry(w + 8, h + 8);
    this.disposables.push(glowGeo);
    const faceGeo = new THREE.PlaneGeometry(w, h);
    this.disposables.push(faceGeo);

    let i = 0;
    for (const node of graph.nodes) {
      const at = layout.pos.get(node.id);
      if (!at) continue;
      const verified = node.verified;
      const group = new THREE.Group();
      group.position.set(at.x, at.y, at.z);

      const body = new THREE.Mesh(bodyGeo, new THREE.MeshBasicMaterial({ color: new THREE.Color(this.pal.surface3).multiplyScalar(0.7) }));
      body.userData.nodeId = node.id;
      group.add(body);

      const face = new THREE.Mesh(faceGeo, new THREE.MeshBasicMaterial({ map: this.makeFace(node), transparent: !verified, opacity: verified ? 1 : 0.78 }));
      face.position.z = 0.115;
      group.add(face);

      const frameMat: THREE.LineBasicMaterial | THREE.LineDashedMaterial = verified
        ? new THREE.LineBasicMaterial({ color: accent, transparent: true, opacity: 0.95 })
        : new THREE.LineDashedMaterial({ color: new THREE.Color(this.pal.lineStrong).lerp(new THREE.Color(this.pal.text3), 0.5), dashSize: 0.22, gapSize: 0.16, transparent: true, opacity: 0.9 });
      const frame = new THREE.Line(edgeGeo, frameMat);
      if (!verified) frame.computeLineDistances();
      frame.position.z = 0.01;
      group.add(frame);

      const glowMat = new THREE.ShaderMaterial({
        vertexShader: GLOW_VERT, fragmentShader: GLOW_FRAG, transparent: true, depthWrite: false,
        blending: this.light ? THREE.NormalBlending : THREE.AdditiveBlending,
        uniforms: { uColor: { value: accent.clone() }, uStrength: { value: verified ? (this.light ? 0.35 : 0.5) : 0.0 }, uHalf: { value: new THREE.Vector2(w / 2, h / 2) } },
      });
      const glow = new THREE.Mesh(glowGeo, glowMat);
      glow.position.z = -0.2;
      group.add(glow);

      this.scene.add(group);
      this.nodes.push({ node, group, body, frame, frameMat, glow, glowMat, hover: 0, delay: 0.25 + i * 0.07 });
      i++;
    }
  }

  private port(id: number, side: "out" | "in"): THREE.Vector3 {
    const { layout } = this.o;
    const p = layout.pos.get(id)!;
    const [fx, fy] = layout.flow;
    const sgn = side === "out" ? 1 : -1;
    return new THREE.Vector3(p.x + fx * sgn * (layout.nodeW / 2), p.y + fy * sgn * (layout.nodeH / 2), p.z);
  }

  private buildEdges() {
    const { graph, layout } = this.o;
    const tall = layout.orientation === "tall";
    const accent = new THREE.Color(this.pal.accent);
    const dim = new THREE.Color(this.light ? this.pal.text3 : this.pal.lineStrong).lerp(new THREE.Color(this.pal.text3), 0.35);
    const blending = this.light ? THREE.NormalBlending : THREE.AdditiveBlending;
    const timeU = this.timeUniforms[0];
    const scaleU = this.scaleUniforms[0];
    const radial = this.heavy ? 8 : 5, seg = this.heavy ? 72 : 40;
    const perp = tall ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
    const reducedFreeze = this.o.reducedMotion;

    for (const edge of graph.edges) {
      if (!layout.pos.has(edge.from) || !layout.pos.has(edge.to)) continue;
      const a = this.port(edge.from, "out"), b = this.port(edge.to, "in");
      const flows = edge.take === "winner" ? graph.flows.filter(f => f.edgeId === edge.id) : [];
      const lanes: (FlowSide | null)[] = flows.length ? flows : [null];
      lanes.forEach((flow, li) => {
        const off = flows.length > 1 ? (li === 0 ? -0.34 : 0.34) : 0;
        const A = a.clone().addScaledVector(perp, off), B = b.clone().addScaledVector(perp, off);
        const [fx, fy] = layout.flow;
        const along = Math.abs((B.x - A.x) * fx + (B.y - A.y) * fy);
        const k = Math.max(0.6, along * 0.5);
        const P1 = A.clone().add(new THREE.Vector3(fx * k, fy * k, 0));
        const P2 = B.clone().sub(new THREE.Vector3(fx * k, fy * k, 0));
        if (edge.take === "loser") {
          // behind the panels and (tall) around them, so loser edges don't cut through other nodes
          const side = tall ? (A.x >= 0 ? 1 : -1) * 4.5 : 0;
          P1.z -= 2.4; P2.z -= 2.4;
          if (tall) { P1.x += side; P2.x += side; }
        }
        const curve = new THREE.CubicBezierCurve3(A, P1, P2, B);
        const isFav = !!flow?.favourite;
        const p = flow?.pWin ?? 0;
        const radius = flow ? (isFav ? 0.075 : 0.04) * (0.8 + 0.5 * p) : 0.03;
        const geo = new THREE.TubeGeometry(curve, seg, radius, radial, false);
        const confirmed = edge.confirmed;
        const color = flow ? (isFav ? accent.clone() : dim.clone().lerp(new THREE.Color(this.pal.text2), 0.25)) : dim.clone();
        const mat = new THREE.ShaderMaterial({
          vertexShader: PATH_VERT, fragmentShader: PATH_FRAG, transparent: true, depthWrite: false, blending,
          uniforms: {
            uColor: { value: color }, uOpacity: { value: flow ? (isFav ? 0.95 : 0.55) : this.light ? 0.75 : 0.6 },
            uDash: { value: confirmed ? 0 : 1 }, uLen: { value: curve.getLength() },
            uTime: reducedFreeze ? { value: 0 } : timeU, uPulse: { value: flow ? (isFav ? 1 : 0.35) : 0 }, uPhase: { value: li * 0.5 },
          },
        });
        const mesh = new THREE.Mesh(geo, mat);
        this.scene.add(mesh);

        const lane: Lane = { edge, curve, flow, points: null, token: null, tokenPhase: li * 0.5, mat, pMat: null, size: 0 };
        if (flow) this.addFlowParticles(lane, A, P1, P2, B, perp, { timeU: reducedFreeze ? { value: 0.35 } : timeU, scaleU, blending });
        this.lanes.push(lane);
      });
    }
  }

  private addFlowParticles(lane: Lane, A: THREE.Vector3, P1: THREE.Vector3, P2: THREE.Vector3, B: THREE.Vector3, perp: THREE.Vector3,
    u: { timeU: { value: number }; scaleU: { value: number }; blending: THREE.Blending }) {
    const flow = lane.flow!;
    const p = flow.pWin;
    const base = this.heavy ? 620 : 120;
    const count = Math.round(base * (0.25 + 0.75 * p) * (flow.favourite ? 1.15 : 0.8));
    const packets = 6;
    const ph = new Float32Array(count), rnd = new Float32Array(count * 4), pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const pk = Math.floor(Math.random() * packets);
      ph[i] = (pk + Math.random() * 0.1) / packets;
      for (let k = 0; k < 4; k++) rnd[i * 4 + k] = Math.random();
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aPhase", new THREE.BufferAttribute(ph, 1));
    geo.setAttribute("aRand", new THREE.BufferAttribute(rnd, 4));
    const color = flow.favourite ? new THREE.Color(this.pal.accent) : new THREE.Color(this.pal.text3);
    if (!this.light) color.multiplyScalar(flow.favourite ? 1.6 : 0.9);
    const mat = new THREE.ShaderMaterial({
      vertexShader: PARTICLE_VERT, fragmentShader: PARTICLE_FRAG, transparent: true, depthWrite: false, blending: u.blending,
      uniforms: {
        uP0: { value: A }, uP1: { value: P1 }, uP2: { value: P2 }, uP3: { value: B }, uSide: { value: perp.clone() },
        uTime: u.timeU, uSpeed: { value: 0.09 + 0.05 * p }, uSize: { value: (flow.favourite ? 7.5 : 5) * (0.7 + 0.6 * p) },
        uScale: u.scaleU, uSpread: { value: flow.favourite ? 0.42 : 0.3 }, uColor: { value: color },
        uIntensity: { value: flow.favourite ? 1.0 : 0.55 },
      },
    });
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    this.scene.add(pts);
    lane.points = pts; lane.pMat = mat;
    lane.size = (flow.favourite ? 1.15 : 0.8) * (0.7 + 0.6 * p);
  }

  private buildLabels() {
    const { layout } = this.o;
    for (const l of layout.labels) {
      const s = textSprite(l.text, this.pal.text3, this.pal.display, 44);
      s.material.opacity = 0.9;
      s.position.set(l.x, l.y, l.z);
      this.scene.add(s);
    }
    // projected-path legend lives in the DOM overlay; nothing else to draw here
  }

  private async loadLogos() {
    const loader = new THREE.TextureLoader();
    const { layout, graph } = this.o;
    const cache = new Map<string, Promise<{ tex: THREE.Texture; dark: boolean } | null>>();
    const get = (src: string) => {
      let p = cache.get(src);
      if (!p) { p = loadLogoTexture(loader, src, this.renderer); cache.set(src, p); }
      return p;
    };
    const w = layout.nodeW, h = layout.nodeH;
    const plateGeo = new THREE.PlaneGeometry(1, 1);
    this.disposables.push(plateGeo);
    const tokenPlate = (() => {
      const c = document.createElement("canvas"); c.width = c.height = 64;
      const g = c.getContext("2d")!; g.fillStyle = "#fff"; g.beginPath(); g.arc(32, 32, 30, 0, Math.PI * 2); g.fill();
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; this.textures.push(t); return t;
    })();

    await Promise.all(this.nodes.map(async nv => {
      const m = nv.node.match;
      if (!m) return;
      await Promise.all(m.sides.map(async (side, si) => {
        if (!side.logo) return;
        const got = await get(side.logo);
        if (this.disposed) { got?.tex.dispose(); return; }
        if (!got) return;
        if (!this.textures.includes(got.tex)) this.textures.push(got.tex);
        const plateColor = new THREE.Color(got.dark ? this.pal.plateDark : this.light ? "#ffffff" : this.pal.plate);
        const s = 1.06, y0 = h / 2 - ((48 + si * 104 + 52) / FACE_H) * h;
        const plate = new THREE.Mesh(plateGeo, new THREE.MeshBasicMaterial({ color: plateColor }));
        plate.scale.set(s, s, 1); plate.position.set(-w / 2 + (62 / FACE_W) * w, y0, 0.13);
        const logo = new THREE.Mesh(plateGeo, new THREE.MeshBasicMaterial({ map: got.tex, transparent: true }));
        logo.scale.set(s * 0.86, s * 0.86, 1); logo.position.set(plate.position.x, y0, 0.135);
        nv.group.add(plate, logo);

        // team token travelling along its own lane
        const lane = this.lanes.find(l => l.flow && l.flow.nodeId === nv.node.id && l.flow.teamId === side.team_id);
        if (lane) {
          const flow = lane.flow!;
          const tok = new THREE.Group();
          const sz = 0.95 * (0.7 + 0.6 * flow.pWin);
          const back = new THREE.Sprite(new THREE.SpriteMaterial({ map: tokenPlate, color: plateColor, transparent: true, depthWrite: false }));
          const fg = new THREE.Sprite(new THREE.SpriteMaterial({ map: got.tex, transparent: true, depthWrite: false }));
          back.scale.set(sz, sz, 1); fg.scale.set(sz * 0.8, sz * 0.8, 1);
          back.renderOrder = 5; fg.renderOrder = 6;
          tok.add(back, fg);
          tok.userData.back = back; tok.userData.fg = fg; tok.userData.size = sz;
          this.scene.add(tok);
          lane.token = tok;
          this.placeToken(lane, 0.3);
        }
      }));
    }));
    void graph;
    this.markDirty();
  }

  private placeToken(lane: Lane, u: number) {
    if (!lane.token) return;
    lane.curve.getPoint(clamp01(u), lane.token.position);
    const fade = Math.min(1, u / 0.1, (1 - u) / 0.1);
    const dimm = lane.flow!.favourite ? 1 : 0.6;
    for (const k of ["back", "fg"] as const) {
      const s = lane.token.userData[k] as THREE.Sprite;
      s.material.opacity = clamp01(fade) * dimm;
    }
    lane.token.visible = fade > 0.01;
  }

  /* ------------------------------------------------------------ events */

  private markDirty = () => { this.dirty = true; };

  private onContextLost = (e: Event) => { e.preventDefault(); this.o.onLost(); };

  private onControlStart = () => {
    this.userMoved = true;
    if (this.intro) this.intro = false;
    this.reset = null;
  };

  private onPointerMove = (e: PointerEvent) => {
    this.pointerType = e.pointerType;
    const r = this.canvas.getBoundingClientRect();
    this.pointerNdc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    if (e.pointerType === "mouse") this.pointerDirty = true;
  };

  private onPointerDown = (e: PointerEvent) => {
    this.down = { x: e.clientX, y: e.clientY, t: performance.now() };
  };

  private onPointerUp = (e: PointerEvent) => {
    const d = this.down; this.down = null;
    if (!d || !this.interactive) return;
    if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 6 || performance.now() - d.t > 600) return;
    const r = this.canvas.getBoundingClientRect();
    this.pointerNdc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.select(this.pick());
  };

  private onPointerLeave = () => { this.pointerDirty = false; if (this.pointerType === "mouse") this.hover(null); };

  private pick(): NodeView | null {
    this.raycaster.setFromCamera(this.pointerNdc, this.camera);
    const hits = this.raycaster.intersectObjects(this.nodes.map(n => n.body), false);
    const id = hits[0]?.object.userData.nodeId as number | undefined;
    return id == null ? null : this.nodes.find(n => n.node.id === id) ?? null;
  }

  private screenOf(nv: NodeView): PickInfo {
    const r = this.canvas.getBoundingClientRect();
    const half = (this.o.layout.nodeW / 2) * nv.group.scale.x;
    const hh = (this.o.layout.nodeH / 2) * nv.group.scale.y;
    const at = (dx: number, dy: number) => {
      const v = nv.group.position.clone();
      v.x += dx; v.y += dy;
      v.project(this.camera);
      return { x: ((v.x + 1) / 2) * r.width, y: ((1 - v.y) / 2) * r.height };
    };
    const top = at(0, hh), rt = at(half, 0), lf = at(-half, 0);
    return { id: nv.node.id, x: top.x, y: top.y, rx: rt.x, lx: lf.x, my: rt.y };
  }

  private hover(nv: NodeView | null) {
    if (nv === this.hovered) return;
    this.hovered = nv;
    this.canvas.style.cursor = nv ? "pointer" : "";
    this.o.onHover(nv ? this.screenOf(nv) : null);
    this.markDirty();
  }

  private select(nv: NodeView | null) {
    this.selected = nv === this.selected ? null : nv;
    if (this.selected) { const s = this.screenOf(this.selected); this.lastSel = { x: s.x, y: s.y }; this.o.onSelect(s); }
    else this.o.onSelect(null);
    this.markDirty();
  }

  private resize() {
    if (this.disposed) return;
    const c = this.o.container;
    const w = Math.max(1, c.clientWidth), h = Math.max(1, c.clientHeight);
    this.renderer.setSize(w, h, false);
    this.composer?.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    const before = this.homeDist;
    this.computeHome(w / h);
    this.applyDistanceLimits();
    if (!this.userMoved && !this.intro) {
      this.camera.position.copy(this.homeTarget).add(this.homeOffset);
      this.controls.target.copy(this.homeTarget);
    } else if (before !== this.homeDist) {
      this.markDirty();
    }
    this.markDirty();
  }

  /* ------------------------------------------------------------ frame */

  private frame = (now: number) => {
    if (this.disposed) return;
    this.raf = requestAnimationFrame(this.frame);
    if (!this.visible || document.hidden) { this.last = now; return; }
    const dt = Math.min(0.05, Math.max(0, (now - (this.last || now)) / 1000));
    this.last = now;
    const reduced = this.o.reducedMotion;
    let animating = false;

    if (!reduced) { this.time += dt; for (const t of this.timeUniforms) t.value = this.time; animating = true; }

    if (this.intro) {
      this.introT += dt;
      const k = ease(clamp01(this.introT / this.introDur));
      const target = this.homeTarget;
      const end = target.clone().add(this.homeOffset);
      // interpolate in spherical space so the fly-in arcs rather than cutting a straight line
      const s0 = new THREE.Spherical().setFromVector3(this.introFrom.clone().sub(target));
      const s1 = new THREE.Spherical().setFromVector3(this.homeOffset);
      const s = new THREE.Spherical(s0.radius + (s1.radius - s0.radius) * k, s0.phi + (s1.phi - s0.phi) * k, s0.theta + (s1.theta - s0.theta) * k);
      this.camera.position.copy(target).add(new THREE.Vector3().setFromSpherical(s));
      this.controls.target.copy(target);
      if (this.introT >= this.introDur) { this.intro = false; this.camera.position.copy(end); }
      animating = true;
    } else if (this.reset) {
      this.reset.t += dt;
      const k = ease(clamp01(this.reset.t / 0.9));
      const end = this.homeTarget.clone().add(this.homeOffset);
      this.camera.position.lerpVectors(this.reset.fromPos, end, k);
      this.controls.target.lerpVectors(this.reset.fromTarget, this.homeTarget, k);
      if (this.reset.t >= 0.9) this.reset = null;
      animating = true;
    }

    const moved = this.controls.update(dt);
    if (this.clampPan()) { /* position corrected */ }

    // node pop-in + hover easing
    const introK = this.intro ? this.introT : 99;
    for (const nv of this.nodes) {
      const pop = reduced ? 1 : easeOut(clamp01((introK - nv.delay) / 0.7));
      const goal = nv === this.hovered || nv === this.selected ? 1 : 0;
      nv.hover += (goal - nv.hover) * Math.min(1, dt * 10);
      if (Math.abs(goal - nv.hover) > 0.004) animating = true;
      const sc = (0.55 + 0.45 * pop) * (1 + 0.045 * nv.hover);
      nv.group.scale.setScalar(sc);
      nv.group.visible = pop > 0.01;
      nv.glowMat.uniforms.uStrength.value = (nv.node.verified ? (this.light ? 0.35 : 0.5) : 0) + nv.hover * (this.light ? 0.4 : 0.8) + (nv.node.verified && !reduced ? 0.08 * Math.sin(this.time * 1.6 + nv.node.id) : 0);
      if (nv.frameMat instanceof THREE.LineBasicMaterial && !(nv.frameMat instanceof THREE.LineDashedMaterial)) {
        nv.frameMat.color.set(this.pal.accent).multiplyScalar(0.75 + 0.25 * nv.hover + (this.useBloom() ? 0.5 * nv.hover : 0));
      } else {
        nv.frameMat.color.set(nv.hover > 0.5 ? this.pal.accent2 : this.pal.lineStrong).lerp(new THREE.Color(this.pal.text3), nv.hover > 0.5 ? 0 : 0.5);
      }
    }
    if (animating && !reduced) { /* pop animations count as dirty below */ }

    // hover raycast (mouse only, coalesced to one per frame)
    if (this.pointerDirty && this.interactive && !this.down) {
      this.pointerDirty = false;
      this.hover(this.pick());
    }

    // team tokens
    for (const lane of this.lanes) {
      if (!lane.token) continue;
      const u = reduced ? 0.3 : ((this.time * (0.075 + 0.04 * (lane.flow?.pWin ?? 0.5)) + lane.tokenPhase) % 1);
      this.placeToken(lane, u);
    }

    // keep a pinned tooltip glued to its node
    if (this.selected && (moved || animating)) {
      const s = this.screenOf(this.selected);
      if (Math.hypot(s.x - this.lastSel.x, s.y - this.lastSel.y) >= 1) { this.lastSel = { x: s.x, y: s.y }; this.o.onSelect(s); }
    }

    if (reduced && !this.dirty && !moved && !animating) return;
    this.dirty = false;
    if (this.composer) this.composer.render(dt); else this.renderer.render(this.scene, this.camera);
  };

  private clampPan(): boolean {
    const o = this.o.layout.overview, t = this.controls.target;
    const x = Math.min(o.maxX + 3, Math.max(o.minX - 3, t.x));
    const y = Math.min(o.maxY + 3, Math.max(o.minY - 3, t.y));
    const z = Math.min(4, Math.max(-14, t.z));
    if (x === t.x && y === t.y && z === t.z) return false;
    const d = new THREE.Vector3(x - t.x, y - t.y, z - t.z);
    t.add(d); this.camera.position.add(d);
    return true;
  }
}
