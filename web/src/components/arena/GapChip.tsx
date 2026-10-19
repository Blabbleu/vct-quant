import { Chip } from "./Chip";
import { COPY, MIN_TRUSTED_VOLUME } from "../../lib/constants";
import { gapPresentation } from "../../lib/gapPresentation";

/**
 * Model-minus-market gap for team A, as the spec's table:
 *   <1pt AGREE (grey) · 1-10pt neutral surface · >=10pt BIG GAP (gold fill).
 * No market renders the placeholder line instead of a chip; a wide spread
 * renders the quoted delta subdued with an explicit WIDE SPREAD label.
 * `favouredLabel` (e.g. "NRG FAVOURED") is an optional caller-supplied read
 * used only in the no-market case, since GapChip itself only sees numbers.
 */
export default function GapChip({ model, market, spread, volume, favouredLabel }: {
  model: number; market: number | null | undefined; spread?: number | null; volume?: number | null; favouredLabel?: string;
}) {
  const presentation = gapPresentation(model, market, spread, volume);

  if (presentation.kind === "no-price") {
    return (
      <span className="gapchip-noprice">
        <span className="gapchip-ph num">{COPY.noMarket}</span>
        {favouredLabel && <span className="gapchip-read">{favouredLabel}</span>}
      </span>
    );
  }

  const gapPts = presentation.gapPoints;
  const abs = Math.abs(gapPts);
  const sign = gapPts < -0.05 ? "\u2212" : gapPts > 0.05 ? "+" : "";
  const text = `\u0394 ${sign}${abs.toFixed(1)}`;

  const wide = presentation.kind === "wide";
  const variant = wide ? "wide" : presentation.kind;
  const suffix = variant === "agree" ? " \u00B7 AGREE" : variant === "big" ? " \u00B7 BIG GAP" : "";

  return (
    <span className="gapchip-wrap">
      <Chip variant={variant === "big" ? "market" : variant === "agree" || wide || variant === "untrusted" ? "ghost" : "default"}>
        <span className="num">{text}</span>{suffix}
      </Chip>
      {wide && <Chip variant="ghost">WIDE SPREAD</Chip>}
      {variant === "untrusted" && <Chip variant="ghost">{volume != null && volume < MIN_TRUSTED_VOLUME ? "LOW VOLUME" : "UNTRUSTED PRICE"}</Chip>}
    </span>
  );
}
