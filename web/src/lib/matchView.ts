/**
 * Pure helpers for the match page, so orientation bugs are testable.
 *
 * `pA` is the model's probability that team A wins; `marketA` is the market's price for team A.
 * The hero panel quotes the FAVOURITE (the side the model prefers), so its Model, Market and
 * model-minus-market gap must all be taken on that same side.
 */
export type Side = "a" | "b";

export interface SideView {
  side: Side;
  /** Probability (0..1) that this side wins, per the model. */
  model: number;
  /** Market price (0..1) for the same side, or null without a market. */
  market: number | null;
  /** model - market in percentage points, same side, or null without a market. */
  gapPts: number | null;
}

export function favouriteSide(pA: number): Side { return pA >= 0.5 ? "a" : "b"; }

export function sideView(pA: number, marketA: number | null | undefined, side: Side): SideView {
  const model = side === "a" ? pA : 1 - pA;
  const market = marketA == null ? null : side === "a" ? marketA : 1 - marketA;
  return { side, model, market, gapPts: market == null ? null : (model - market) * 100 };
}

/** Collision-free vertical positions for end-of-line labels (min `gap` px apart, inside [lo, hi]). */
export function spreadLabels(ys: number[], gap: number, lo: number, hi: number): number[] {
  const order = ys.map((y, i) => ({ y, i })).sort((p, q) => p.y - q.y);
  const out = order.map(o => Math.min(Math.max(o.y, lo), hi));
  // Push down to satisfy the gap, then pull back up if we ran past the bottom.
  for (let k = 1; k < out.length; k++) if (out[k] - out[k - 1] < gap) out[k] = out[k - 1] + gap;
  for (let k = out.length - 1; k >= 0; k--) {
    const limit = k === out.length - 1 ? hi : out[k + 1] - gap;
    if (out[k] > limit) out[k] = limit;
  }
  const res = new Array<number>(ys.length);
  order.forEach((o, k) => { res[o.i] = out[k]; });
  return res;
}
