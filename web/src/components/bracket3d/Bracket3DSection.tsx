import { Component, lazy, Suspense, useState, type ReactNode } from "react";
import type { ChampionsPlayoffs } from "../../lib/types";
import SectionHead from "../arena/SectionHead";
import { Chip } from "../arena/Chip";

/**
 * Lazy-loaded 3D bracket with a graceful exit: no WebGL, a failed chunk, a renderer error or a
 * lost GPU context all collapse to `null`, leaving the 2D playoffs section as the only view.
 * `?b3d=off` forces that fallback; `?b3d=light|heavy` forces a quality tier (testing).
 */
const Bracket3D = lazy(() => import("./Bracket3D"));

export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    const gl = (c.getContext("webgl2") ?? c.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return false;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

function pickQuality(): "heavy" | "light" | null {
  const q = new URLSearchParams(location.search).get("b3d");
  if (q === "off") return null;
  if (q === "light" || q === "heavy") return q;
  return window.matchMedia("(min-width: 1024px) and (not (pointer: coarse))").matches ? "heavy" : "light";
}

class Boundary extends Component<{ onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(err: unknown) { console.warn("Bracket3D failed to load", err); this.props.onError(); }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function Bracket3DSection({ playoffs }: { playoffs: ChampionsPlayoffs }) {
  const [quality] = useState(pickQuality);
  const [ok, setOk] = useState(() => quality != null && webglAvailable());
  if (!ok || !quality) return null;
  return (
    <section className="b3d-section" aria-label="3D bracket">
      <SectionHead title="Bracket in 3D" right={<Chip variant="ghost">ROUTING UNCONFIRMED</Chip>} />
      <Boundary onError={() => setOk(false)}>
        <Suspense fallback={<p className="b3d-fallback-msg">Loading 3D bracket&hellip;</p>}>
          <Bracket3D playoffs={playoffs} quality={quality} onUnavailable={() => setOk(false)} />
        </Suspense>
      </Boundary>
    </section>
  );
}
