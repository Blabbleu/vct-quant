import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChampionsPlayoffs } from "../../lib/types";
import { buildBracketGraph, feedLabel } from "../../lib/bracketGraph";
import { utc } from "../../lib/format";
import { BracketEngine, type CameraState, type PickInfo, type Quality, type ThemeName } from "./engine";
import { layoutBracket, type Orientation } from "./layout";
import "./Bracket3D.css";

/** Lazy 3D module entry. Calls onUnavailable if WebGL or the renderer fails after mount. */
export default function Bracket3D({ playoffs, quality, onUnavailable }: {
  playoffs: ChampionsPlayoffs; quality: Quality; onUnavailable: () => void;
}) {
  const graph = useMemo(() => buildBracketGraph(playoffs), [playoffs]);
  const hostRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<BracketEngine | null>(null);
  const camRef = useRef<CameraState | null>(null);
  const [theme, setTheme] = useState<ThemeName>(readTheme);
  const [orientation, setOrientation] = useState<Orientation>("wide");
  const [hover, setHover] = useState<PickInfo | null>(null);
  const [sel, setSel] = useState<PickInfo | null>(null);
  const [active, setActive] = useState(quality === "heavy");
  const reduced = useReducedMotion();
  const coarse = quality === "light";

  // follow the app theme (toggle button, or OS change before an explicit choice)
  useEffect(() => {
    const mo = new MutationObserver(() => setTheme(readTheme()));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  // portrait layout on narrow hosts
  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const apply = () => setOrientation(el.clientWidth < 720 ? "tall" : "wide");
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const layout = useMemo(() => layoutBracket(orientation), [orientation]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let engine: BracketEngine;
    try {
      engine = new BracketEngine({
        container: host, graph, layout, quality, theme, reducedMotion: reduced,
        initialCamera: camRef.current,
        onHover: setHover, onSelect: setSel, onLost: onUnavailable,
      });
    } catch (e) {
      console.warn("Bracket3D: renderer unavailable", e);
      onUnavailable();
      return;
    }
    engine.domElement.setAttribute("role", "img");
    engine.domElement.setAttribute("aria-label",
      "Interactive 3D diagram of the Champions 2026 playoff bracket. Teams from the four verified Upper Quarterfinals flow along projected, unconfirmed paths, brighter for a higher model win probability. The same information is listed as text below.");
    engine.setInteractive(!coarse);
    engineRef.current = engine;
    return () => {
      camRef.current = engine.getCameraState();
      engine.dispose();
      engineRef.current = null;
      setHover(null); setSel(null);
    };
    // quality is fixed for the lifetime of the component
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, layout, theme, reduced]);

  // re-apply interaction mode after a rebuild
  useEffect(() => { engineRef.current?.setInteractive(!coarse || active); });

  const reset = useCallback(() => { engineRef.current?.resetView(); }, []);

  const shown = sel ?? hover;
  const node = shown ? graph.byId.get(shown.id) ?? null : null;
  const host = hostRef.current;
  const tipStyle = shown && host ? tipPosition(shown, host.clientWidth, host.clientHeight) : undefined;

  return (
    <div className={`b3d${coarse ? " b3d-touch" : ""}${active ? " b3d-active" : ""}`}>
      <div className="b3d-stage">
        <div ref={hostRef} className="b3d-host" />
        {node && tipStyle && (
          <div className="b3d-tip cut-m" style={tipStyle} role="status">
            <div className="b3d-tip-head">
              <span>{node.stage}</span>
              {node.bestOf && <span className="num">Bo{node.bestOf}</span>}
            </div>
            <div className="b3d-tip-when num">{utc(node.start)}</div>
            {node.match ? (
              <>
                {node.match.sides.map(s => (
                  <div key={s.team_id} className={`b3d-tip-row${(s.p_win ?? 0) > (node.match!.sides.find(o => o !== s)?.p_win ?? 0) ? " b3d-fav" : ""}`}>
                    <span className="b3d-tip-name">{s.tag ?? s.name}</span>
                    <span className="num">{s.p_win != null ? `${(s.p_win * 100).toFixed(1)}%` : "--.-"}</span>
                  </div>
                ))}
                <div className="b3d-tip-note">Model win probability &middot; verified pairing</div>
              </>
            ) : (
              <>
                {node.feeds.map(f => <div key={`${f.from}-${f.take}`} className="b3d-tip-row"><span className="b3d-tip-name">{feedLabel(f)}</span></div>)}
                <div className="b3d-tip-note">Teams TBD &middot; route projected, not officially confirmed</div>
              </>
            )}
          </div>
        )}
        <div className="b3d-ui">
          <button type="button" className="b3d-btn" onClick={reset}>Reset view</button>
          {coarse && active && <button type="button" className="b3d-btn" onClick={() => setActive(false)}>Done</button>}
        </div>
        {coarse && !active && (
          <button type="button" className="b3d-gate" onClick={() => setActive(true)}>
            <span>Tap to explore in 3D</span>
            <small>then drag to rotate &middot; pinch to zoom &middot; swipe page freely until then</small>
          </button>
        )}
      </div>
      <p className="b3d-cap">
        <span className="b3d-key b3d-key-solid" aria-hidden="true" /> Verified opening pairing
        <span className="b3d-key b3d-key-dash" aria-hidden="true" /> Projected route &mdash; not officially confirmed
        <span className="b3d-capnote">Flow brightness = model win probability. Not a title forecast; no team is shown past its opening match.</span>
      </p>
    </div>
  );
}

function readTheme(): ThemeName {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function useReducedMotion(): boolean {
  const [r, setR] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setR(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return r;
}

function tipPosition(p: PickInfo, width: number, height: number): React.CSSProperties {
  const W = 200, H = 120, gap = 14;
  // Prefer the right of the node, then the left, else above/below the node centred on it.
  if (p.rx + gap + W <= width - 4) return { left: p.rx + gap, top: clampTop(p.my - H / 2, height, H), width: W };
  if (p.lx - gap - W >= 4) return { left: p.lx - gap - W, top: clampTop(p.my - H / 2, height, H), width: W };
  const left = Math.min(Math.max(8, p.x - W / 2), Math.max(8, width - W - 8));
  return p.y > H + 16
    ? { left, top: p.y - H - 8, width: W }
    : { left, top: clampTop(p.my + 40, height, H), width: W };
}

function clampTop(top: number, height: number, h: number) {
  return Math.min(Math.max(8, top), Math.max(8, height - h - 8));
}
