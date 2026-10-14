import { AGREE_POINTS, BIG_GAP_POINTS, WIDE_SPREAD } from "./constants.ts";

export type GapPresentation =
  | { kind: "no-price" }
  | { kind: "wide"; gapPoints: number }
  | { kind: "untrusted"; gapPoints: number }
  | { kind: "agree" | "mid" | "big"; gapPoints: number };

/** Classify a model-market quote for display. Wide quotes carry a delta for context, but no edge claim. */
export function gapPresentation(model: number, market: number | null | undefined, spread?: number | null, volume?: number | null): GapPresentation {
  if (market == null) return { kind: "no-price" };

  const gapPoints = (model - market) * 100;
  if (spread != null && spread > WIDE_SPREAD) return { kind: "wide", gapPoints };
  if (spread == null || volume == null || volume < 1000) return { kind: "untrusted", gapPoints };

  const abs = Math.abs(gapPoints);
  return { kind: abs < AGREE_POINTS ? "agree" : abs >= BIG_GAP_POINTS ? "big" : "mid", gapPoints };
}
