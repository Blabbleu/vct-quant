import { Chip } from "./Chip";
import { AGREE_POINTS, BIG_GAP_POINTS, COPY, WIDE_SPREAD } from "../../lib/constants";

/**
 * Model-minus-market gap for team A, as the spec's table:
 *   <1pt AGREE (grey) · 1-10pt neutral surface · >=10pt BIG GAP (pink fill).
 * No market renders the placeholder line instead of a chip; a wide spread
 * renders the market in --text-3 with a WIDE SPREAD chip alongside.
 * `favouredLabel` (e.g. "NRG FAVOURED") is an optional caller-supplied read
 * used only in the no-market case, since GapChip itself only sees numbers.
 */
export default function GapChip({ model, market, spread, favouredLabel }: {
  model: number; market: number | null | undefined; spread?: number | null; favouredLabel?: string;
}) {
  const wide = spread != null && spread > WIDE_SPREAD;

  if (market == null) {
    return (
      <span className="gapchip-noprice">
        <span className="gapchip-ph num">{COPY.noMarket}</span>
        {favouredLabel && <span className="gapchip-read">{favouredLabel}</span>}
      </span>
    );
  }

  const gapPts = (model - market) * 100;
  const abs = Math.abs(gapPts);
  const sign = gapPts < -0.05 ? "\u2212" : gapPts > 0.05 ? "+" : "";
  const text = `\u0394 ${sign}${abs.toFixed(1)}`;

  const variant: "agree" | "mid" | "big" =
    abs < AGREE_POINTS ? "agree" : abs >= BIG_GAP_POINTS ? "big" : "mid";
  const suffix = variant === "agree" ? " \u00B7 AGREE" : variant === "big" ? " \u00B7 BIG GAP" : "";

  return (
    <span className="gapchip-wrap">
      <Chip variant={variant === "big" ? "market" : variant === "agree" ? "ghost" : "default"}>
        <span className="num">{text}</span>{suffix}
      </Chip>
      {wide && <Chip variant="ghost">WIDE SPREAD</Chip>}
    </span>
  );
}
