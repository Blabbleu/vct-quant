/**
 * Where each bracket node sits in 3D space. Pure data (no three.js) so it is cheap to test.
 *
 * "wide": rounds run left -> right, upper bracket above the lower one (desktop / landscape).
 * "tall": rounds run top -> bottom, upper block first (portrait phones, where 5-6 columns
 *         would be unreadably small). The lower bracket is shifted one round along the flow
 *         in "wide" so loser edges always travel forward.
 */
export type Orientation = "wide" | "tall";

export interface Placed { x: number; y: number; z: number }
export interface Box { minX: number; maxX: number; minY: number; maxY: number }
export interface SectionLabel { text: string; x: number; y: number; z: number }

export interface BracketLayout {
  orientation: Orientation;
  nodeW: number;
  nodeH: number;
  /** Unit vector (x, y) in the bracket plane pointing the way rounds advance. */
  flow: readonly [number, number];
  pos: ReadonlyMap<number, Placed>;
  /** Everything, including node extents. */
  overview: Box;
  /** What the camera frames first (all of it in "wide"; all but the last three nodes in "tall"). */
  home: Box;
  labels: SectionLabel[];
}

const NODE_W = 5.2;
const NODE_H = 2.6;

/** [match_id, x-or-column, y-or-row, z-depth group]. Column/row units are scaled below. */
type Row = readonly [number, number, number, "upper" | "lower" | "final"];

// Wide: x = column, y = world units (up).
const WIDE: Row[] = [
  [754730, 0, 12.4, "upper"], [754731, 0, 8.8, "upper"], [754732, 0, 5.2, "upper"], [754733, 0, 1.6, "upper"],
  [754734, 1, 10.6, "upper"], [754735, 1, 3.4, "upper"],
  [754736, 2, 7, "upper"],
  [754738, 1, -6.2, "lower"], [754739, 1, -9.8, "lower"],
  [754740, 2, -6.2, "lower"], [754741, 2, -9.8, "lower"],
  [754742, 3, -8, "lower"],
  [754743, 4, -8, "lower"],
  [754737, 5, -0.5, "final"],
];
const COL = 6.6;

// Tall: x = world units, y = row (down).
const TALL: Row[] = [
  [754730, -8.4, 0, "upper"], [754731, -2.8, 0, "upper"], [754732, 2.8, 0, "upper"], [754733, 8.4, 0, "upper"],
  [754734, -5.6, 1, "upper"], [754735, 5.6, 1, "upper"],
  [754736, 0, 2, "upper"],
  [754738, -2.8, 3.6, "lower"], [754739, 2.8, 3.6, "lower"],
  [754740, -2.8, 4.6, "lower"], [754741, 2.8, 4.6, "lower"],
  [754742, 0, 5.6, "lower"],
  [754743, 0, 6.6, "lower"],
  [754737, 0, 8.2, "final"],
];
const ROW = 5.6;

export function layoutBracket(orientation: Orientation): BracketLayout {
  const pos = new Map<number, Placed>();
  const tall = orientation === "tall";
  for (const [id, a, b, grp] of tall ? TALL : WIDE) {
    const depth = tall ? b * 0.6 : a * 0.9;
    const z = -depth - (grp === "lower" ? 2.5 : grp === "final" ? 1 : 0);
    pos.set(id, tall ? { x: a, y: -b * ROW, z } : { x: a * COL, y: b, z });
  }
  const boxOf = (ids?: number[]): Box => {
    const b: Box = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity };
    for (const [id, p] of pos) {
      if (ids && !ids.includes(id)) continue;
      b.minX = Math.min(b.minX, p.x - NODE_W / 2); b.maxX = Math.max(b.maxX, p.x + NODE_W / 2);
      b.minY = Math.min(b.minY, p.y - NODE_H / 2); b.maxY = Math.max(b.maxY, p.y + NODE_H / 2);
    }
    return b;
  };
  const overview = boxOf();
  // Tall: frame full width, down to the second lower round, so nodes stay legible on a phone;
  // the rest (Lower R3, Lower Final, Grand Final) is a pan away.
  const home = tall ? boxOf([754730, 754731, 754732, 754733, 754734, 754735, 754736, 754738, 754739, 754740, 754741]) : overview;
  const upper = boxOf([754730, 754731, 754732, 754733, 754734, 754735, 754736]);
  const lower = boxOf([754738, 754739, 754740, 754741, 754742, 754743]);
  const final = boxOf([754737]);
  const labels: SectionLabel[] = [
    { text: "UPPER BRACKET", x: upper.minX, y: upper.maxY + 1.4, z: 0 },
    { text: "LOWER BRACKET", x: lower.minX, y: lower.maxY + 1.4, z: -2.5 },
    { text: "GRAND FINAL", x: final.minX, y: final.maxY + 1.4, z: -1 },
  ];
  // Labels float at the depth of their section's first node.
  [754730, 754738, 754737].forEach((id, i) => { labels[i].z = pos.get(id)?.z ?? 0; });
  return {
    orientation, nodeW: NODE_W, nodeH: NODE_H,
    flow: tall ? [0, -1] : [1, 0],
    pos, overview, home, labels,
  };
}
