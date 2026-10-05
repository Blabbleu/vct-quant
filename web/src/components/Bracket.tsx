import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import LogoSlot from "./arena/LogoSlot";
import { Chip } from "./arena/Chip";
import SectionHead from "./arena/SectionHead";
import { m, useInitial, CountUp, EASE_OUT, D_BASE } from "../lib/motion";
import { buildBracketGraph, dropTargets, feedLabel, progressionEdges, type BracketNode, type RoundKey } from "../lib/bracketGraph";
import type { ChampionsPlayoffs, ChampionsPlayoffSide } from "../lib/types";
import "./Bracket.css";

/* ---------------------------------------------------------------------------
   Layout. Widths are in a 1000-unit design space that maps to 100% of the canvas
   (so the chart is fluid on desktop); heights are real pixels. The SVG overlay uses
   the same space with preserveAspectRatio="none" and non-scaling strokes.
   Columns: 0..3 are rounds, 4 is the Grand Final. The upper row has UQF/USF/UF in
   columns 0-2, the lower row LR1/LR2/LR3/LF in columns 0-3.
   --------------------------------------------------------------------------- */
const COL_W = 176;
const COL_GAP = 30;
const NODE_H = 68;
const PITCH = 86;
const colX = (c: number) => c * (COL_W + COL_GAP);
const U_TOP = 66;                                  // first UQF node top
const L_TOP = 478;                                 // first LR1 node top
const HEIGHT = 640;

interface Slot { col: number; cy: number }

const cy = (top: number, i: number) => top + NODE_H / 2 + i * PITCH;
const UQF = [0, 1, 2, 3].map(i => cy(U_TOP, i));
const USF = [(UQF[0] + UQF[1]) / 2, (UQF[2] + UQF[3]) / 2];
const UF_Y = (USF[0] + USF[1]) / 2;
const LR = [cy(L_TOP, 0), cy(L_TOP, 1)];
const LR3_Y = (LR[0] + LR[1]) / 2;
const GF_Y = (UF_Y + LR3_Y) / 2;

const SLOTS: Record<string, Slot> = {
  UQF1: { col: 0, cy: UQF[0] }, UQF2: { col: 0, cy: UQF[1] }, UQF3: { col: 0, cy: UQF[2] }, UQF4: { col: 0, cy: UQF[3] },
  USF1: { col: 1, cy: USF[0] }, USF2: { col: 1, cy: USF[1] }, UF: { col: 2, cy: UF_Y },
  "LR1-1": { col: 0, cy: LR[0] }, "LR1-2": { col: 0, cy: LR[1] },
  "LR2-1": { col: 1, cy: LR[0] }, "LR2-2": { col: 1, cy: LR[1] },
  LR3: { col: 2, cy: LR3_Y }, LF: { col: 3, cy: LR3_Y }, GF: { col: 4, cy: GF_Y },
};

const ROUND_HEADS: { round: RoundKey; col: number; y: number }[] = [
  { round: "UQF", col: 0, y: 26 }, { round: "USF", col: 1, y: 26 }, { round: "UF", col: 2, y: 26 },
  { round: "LR1", col: 0, y: 440 }, { round: "LR2", col: 1, y: 440 }, { round: "LR3", col: 2, y: 440 }, { round: "LF", col: 3, y: 440 },
  { round: "GF", col: 4, y: GF_Y - NODE_H / 2 - 36 },
];

const HEAD_TEXT: Record<RoundKey, string> = {
  UQF: "Upper quarterfinals", USF: "Upper semifinals", UF: "Upper final",
  LR1: "Lower round 1", LR2: "Lower round 2", LR3: "Lower round 3", LF: "Lower final", GF: "Grand final",
};

/* ------------------------------------------------------------------ helpers */

const dayFmt = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "short", day: "numeric" });
const timeFmt = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false });
const when = (iso: string | null) => (iso ? `${dayFmt.format(new Date(iso))} \u00B7 ${timeFmt.format(new Date(iso))}` : "Time TBD");

function roundSub(nodes: BracketNode[]): string {
  const days = nodes.filter(n => n.start).map(n => new Date(n.start!).getTime()).sort((a, b) => a - b);
  const bo = [...new Set(nodes.map(n => n.bestOf).filter((b): b is number => b != null))];
  const parts: string[] = [];
  if (days.length) {
    const a = dayFmt.format(new Date(days[0])), b = dayFmt.format(new Date(days[days.length - 1]));
    parts.push(a === b ? a : `${a}\u2013${b.replace(/^\w+ /, "")}`);
  }
  if (bo.length) parts.push(bo.map(b => `Bo${b}`).join("/"));
  return parts.join(" \u00B7 ");
}

/** One drawn connector piece. `link` runs from a source box to the join column; `trunk` is the single
 *  shared stub from the join column into the target box (so merged feeders never double-draw it). */
interface Seg { id: string; d: string; col: number; ids: string[] }

/** Join column: the middle of the gap in front of the target box. */
const joinX = (targetCol: number) => colX(targetCol) - COL_GAP / 2;

/**
 * Orthogonal elbows for progression edges only: horizontal out of the source's right edge at its vertical
 * centre, vertical to the target's centre line inside the gap, horizontal into the target. Same-row hops
 * (LR1->LR2, LR3->LF) are a single straight line.
 */
function buildSegs(edges: { id: string; from: string; to: string }[]): Seg[] {
  const byTarget = new Map<string, { id: string; from: string }[]>();
  for (const e of edges) byTarget.set(e.to, [...(byTarget.get(e.to) ?? []), e]);
  const segs: Seg[] = [];
  for (const [to, ins] of byTarget) {
    const t = SLOTS[to];
    const x2 = colX(t.col), xm = joinX(t.col);
    const elbow = ins.some(e => SLOTS[e.from].cy !== t.cy);
    for (const e of ins) {
      const s = SLOTS[e.from];
      const x1 = colX(s.col) + COL_W;
      const d = !elbow ? `M${x1},${s.cy} H${x2}` : s.cy === t.cy ? `M${x1},${s.cy} H${xm}` : `M${x1},${s.cy} H${xm} V${t.cy}`;
      segs.push({ id: e.id, d, col: s.col, ids: [e.id] });
    }
    if (elbow) segs.push({ id: `trunk-${to}`, d: `M${xm},${t.cy} H${x2}`, col: Math.max(...ins.map(e => SLOTS[e.from].col)), ids: ins.map(e => e.id) });
  }
  return segs;
}

/** Everything downstream of a node along winner (progression) edges, as node ids and edge ids. */
function downstream(start: number, edges: { id: string; from: number; to: number }[]) {
  const nodes = new Set<number>([start]);
  const hot = new Set<string>();
  const queue = [start];
  while (queue.length) {
    const cur = queue.pop()!;
    for (const e of edges) {
      if (e.from !== cur) continue;
      hot.add(e.id);
      if (!nodes.has(e.to)) { nodes.add(e.to); queue.push(e.to); }
    }
  }
  return { nodes, edges: hot };
}

/* --------------------------------------------------------------------- node */

const nodeVariants = {
  hidden: { opacity: 0, y: 10 },
  show: (col: number) => ({ opacity: 1, y: 0, transition: { duration: D_BASE, ease: EASE_OUT, delay: col * 0.09 } }),
};
const barVariants = {
  hidden: { scaleX: 0 },
  show: (col: number) => ({ scaleX: 1, transition: { duration: 0.5, ease: EASE_OUT, delay: 0.25 + col * 0.09 } }),
};

function SideRow({ s, fav, tied }: { s: ChampionsPlayoffSide; fav: boolean; tied: boolean }) {
  const tag = (s.tag ?? s.name).toUpperCase();
  return (
    <Link to={`/team/${s.team_id}`} className={`bracket-side${fav && !tied ? " bracket-side-fav" : ""}`} title={s.name}>
      <LogoSlot src={s.logo} name={s.name} tag={s.tag} size={20} />
      <span className="bracket-side-tag">{tag}</span>
      <span className="bracket-side-pct num">
        {s.p_win != null ? <CountUp value={s.p_win * 100} /> : "\u2013"}
      </span>
    </Link>
  );
}

function Node({ n, slot, hot, inPath, dropFrom, onHot }: {
  n: BracketNode; slot: Slot; hot: boolean; inPath: boolean; dropFrom: number | null; onHot: (id: number | null) => void;
}) {
  const isDrop = dropFrom != null && n.feeds.some(f => f.take === "loser" && f.from === dropFrom);
  const verified = n.verified && n.match;
  const sides = verified ? n.match!.sides : null;
  const pA = sides?.[0].p_win ?? null, pB = sides?.[1].p_win ?? null;
  const tied = pA != null && pB != null && pA === pB;
  const favA = pA != null && pB != null ? pA > pB : false;
  const favB = pA != null && pB != null ? pB > pA : false;
  const favP = favA ? pA : favB ? pB : null;
  return (
    <m.div
      className={`bracket-node${verified ? " bracket-node-verified" : " bracket-node-tbd"}${hot ? " is-hot" : ""}${inPath ? " in-path" : ""}${isDrop ? " is-drop" : ""}`}
      style={{ left: `${colX(slot.col) / 10}%`, top: slot.cy - NODE_H / 2, width: `${COL_W / 10}%`, height: NODE_H }}
      custom={slot.col}
      variants={nodeVariants}
      onPointerEnter={e => { if (e.pointerType === "mouse") onHot(n.id); }}
      onPointerLeave={e => { if (e.pointerType === "mouse") onHot(null); }}
      onFocus={() => onHot(n.id)}
      onBlur={() => onHot(null)}
      data-node={n.code}
    >
      <div className="bracket-node-meta">
        <span className="bracket-code">{n.code}</span>
        <span className="num">{verified ? when(n.start) : "TBD"}</span>
      </div>
      {sides ? (
        <>
          <SideRow s={sides[0]} fav={favA} tied={tied} />
          <SideRow s={sides[1]} fav={favB} tied={tied} />
          {favP != null && (
            <span className="bracket-fav-track" aria-hidden="true">
              <m.span className="bracket-fav-fill" style={{ width: `${favP * 100}%`, originX: 0 }} custom={slot.col} variants={barVariants} />
            </span>
          )}
        </>
      ) : (
        n.feeds.map(f => (
          <div className={`bracket-side bracket-side-tbd${f.take === "loser" ? " bracket-side-drop" : ""}${f.take === "loser" && f.from === dropFrom ? " is-drop" : ""}`} key={`${f.take}-${f.from}`}>
            <span className="bracket-tbd-dot" aria-hidden="true" />
            <span className="bracket-tbd-label">{feedLabel(f)}</span>
          </div>
        ))
      )}
    </m.div>
  );
}

/* ------------------------------------------------------------------- chart */

export default function Bracket({ playoffs }: { playoffs: ChampionsPlayoffs }) {
  const graph = useMemo(() => buildBracketGraph(playoffs), [playoffs]);
  const [hotId, setHotId] = useState<number | null>(null);
  const uid = useId().replace(/:/g, "");
  const init = useInitial("hidden");
  const scroller = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(false);
  const [atEnd, setAtEnd] = useState(false);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const measure = () => {
      setOverflowing(el.scrollWidth > el.clientWidth + 2);
      setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 8);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    el.addEventListener("scroll", measure, { passive: true });
    return () => { ro.disconnect(); el.removeEventListener("scroll", measure); };
  }, []);

  const placed = graph.nodes.filter(n => SLOTS[n.code]);
  // Only winner (progression) edges are drawn; loser drop-ins are shown as labels in the lower slots.
  const prog = useMemo(() => progressionEdges(graph.edges).filter(e => {
    const f = graph.byId.get(e.from), t = graph.byId.get(e.to);
    return f && t && SLOTS[f.code] && SLOTS[t.code];
  }), [graph]);
  const segs = useMemo(() => buildSegs(prog.map(e => ({ id: e.id, from: graph.byId.get(e.from)!.code, to: graph.byId.get(e.to)!.code }))), [prog, graph]);
  const confirmed = useMemo(() => new Set(prog.filter(e => e.confirmed).map(e => e.id)), [prog]);

  const path = useMemo(() => (hotId != null ? downstream(hotId, prog) : null), [hotId, prog]);
  // Lower slot(s) the hovered match's loser drops into: highlighted by label/frame, no line.
  const dropFrom = hotId != null && dropTargets(graph, hotId).length > 0 ? hotId : null;
  const rounds = (r: RoundKey) => placed.filter(n => n.round === r);
  const heads = ROUND_HEADS.filter(h => rounds(h.round).length > 0);

  return (
    <section className="champ-bracket" aria-label="Playoff bracket">
      <SectionHead title="Playoff bracket" right={<Chip variant="ghost">ROUTING UNCONFIRMED</Chip>} />
      <p className="champ-sub">
        Upper bracket on top, lower bracket below, Grand Final at the right. Losers drop into the labelled lower slots; hover a match to light up its path. The four opening pairings are official; every
        later slot stays TBD until the API lists its teams. Win % is the primary Elo forecast for the series.
      </p>

      <div className={`bracket-frame${overflowing ? " is-scrollable" : ""}${atEnd ? " at-end" : ""}`}>
        <div className="bracket-scroll" ref={scroller} tabIndex={overflowing ? 0 : undefined} role="group" aria-label="Bracket chart, scrolls sideways on narrow screens">
          <m.div
            className={`bracket-canvas${path ? " has-hot" : ""}`}
            style={{ height: HEIGHT }}
            initial={init}
            whileInView="show"
            viewport={{ once: true, amount: 0.08 }}
          >
            {[0, 1, 2, 3, 4].map(c => (
              <span key={c} className="bracket-snap" style={{ left: `${colX(c) / 10}%` }} aria-hidden="true" />
            ))}

            <span className="bracket-band" style={{ top: 0 }}>Upper bracket</span>
            <span className="bracket-band" style={{ top: 414 }}>Lower bracket</span>

            {heads.map(h => {
              const ns = rounds(h.round);
              return (
                <div key={h.round} className="bracket-head" style={{ left: `${colX(h.col) / 10}%`, top: h.y, width: `${COL_W / 10}%` }}>
                  <span className="bracket-head-name">{HEAD_TEXT[h.round]}</span>
                  <span className="bracket-head-sub num">{roundSub(ns)}</span>
                </div>
              );
            })}

            <svg className="bracket-edges" viewBox={`0 0 1000 ${HEIGHT}`} preserveAspectRatio="none" aria-hidden="true" focusable="false">
              <defs>
                {segs.map(e => (
                  <mask key={e.id} id={`${uid}-${e.id}`} maskUnits="userSpaceOnUse" x="0" y="0" width="1000" height={HEIGHT}>
                    <m.path
                      d={e.d} fill="none" stroke="#fff" strokeWidth={8} vectorEffect="non-scaling-stroke"
                      custom={e.col}
                      variants={{
                        hidden: { pathLength: 0 },
                        show: (col: number) => ({ pathLength: 1, transition: { duration: 0.55, ease: EASE_OUT, delay: 0.3 + col * 0.09 } }),
                      }}
                    />
                  </mask>
                ))}
              </defs>
              {segs.map(e => (
                <path
                  key={e.id}
                  d={e.d}
                  mask={`url(#${uid}-${e.id})`}
                  vectorEffect="non-scaling-stroke"
                  data-edge={e.id}
                  className={`bracket-edge${e.ids.every(i => confirmed.has(i)) ? "" : " bracket-edge-proj"}${e.ids.some(i => path?.edges.has(i)) ? " is-hot" : ""}`}
                />
              ))}
            </svg>

            {placed.map(n => (
              <Node
                key={n.id} n={n} slot={SLOTS[n.code]}
                hot={hotId === n.id} inPath={path?.nodes.has(n.id) ?? false} dropFrom={dropFrom}
                onHot={setHotId}
              />
            ))}
          </m.div>
        </div>
        {overflowing && !atEnd && (
          <div className="bracket-hint" aria-hidden="true"><span>Swipe for later rounds</span><span className="bracket-hint-arrow">&rarr;</span></div>
        )}
      </div>

      <div className="bracket-legend">
        <span className="bracket-legend-item"><svg viewBox="0 0 28 6" width="28" height="6" aria-hidden="true"><path d="M0 3H28" className="bracket-edge bracket-edge-proj" /></svg>Winner advances (projected)</span>
        <span className="bracket-legend-item"><span className="bracket-legend-drop" aria-hidden="true" />Loser drop-in: labelled in the lower slot</span>
        <span className="bracket-legend-note">Projected route &mdash; not officially confirmed. Times in UTC.</span>
      </div>
    </section>
  );
}
