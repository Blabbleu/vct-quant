import { useEffect, useState } from "react";

export type LogoSize = 20 | 34 | 56;

/**
 * Per-logo "is this basically black" cache, keyed by src. Computed once via
 * canvas: the SHARE of opaque pixels that are near-black (luminance < 0.15),
 * flagged dark when that share exceeds 0.5, so it gets the light
 * `--logo-plate-dark` backing in dark theme and doesn't vanish.
 *
 * A plain mean-luminance cutoff can't separate EDG from 100T: EDG's mean is
 * ~0.22 (mostly black background, a little white detail) and 100T's mean is
 * ~0.24 (a light wordmark on transparent, so the few dark pixels drag the
 * mean down too) — raising the mean threshold to include EDG also nets 100T.
 * The near-black pixel SHARE separates them cleanly against real logos:
 * EDG 0.67, Paper Rex 1.0 (solid black mark) both clear 0.5; 100T 0.43 and
 * NRG 0 (no near-black pixels at all) both stay under it.
 * Module-level so every LogoSlot instance for the same team shares one probe.
 */
const darkLogoCache = new Map<string, boolean>();
const NEAR_BLACK_LUM = 0.15;
const NEAR_BLACK_SHARE_THRESHOLD = 0.5;

function computeIsDark(src: string): Promise<boolean> {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      try {
        const w = Math.max(1, Math.min(64, img.naturalWidth || 64));
        const h = Math.max(1, Math.min(64, img.naturalHeight || 64));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) return resolve(false);
        ctx.drawImage(img, 0, 0, w, h);
        const { data } = ctx.getImageData(0, 0, w, h);
        let nearBlack = 0;
        let n = 0;
        for (let i = 0; i < data.length; i += 4) {
          const alpha = data[i + 3];
          if (alpha < 16) continue; // skip transparent pixels
          const r = data[i], g = data[i + 1], b = data[i + 2];
          const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
          if (lum < NEAR_BLACK_LUM) nearBlack++;
          n++;
        }
        resolve(n > 0 && nearBlack / n > NEAR_BLACK_SHARE_THRESHOLD);
      } catch {
        resolve(false); // any canvas error (e.g. tainted): fall back to the normal plate
      }
    };
    img.onerror = () => resolve(false);
    img.src = src;
  });
}

function initialsFor(name: string, tag?: string | null): string {
  if (tag) return tag.slice(0, 3).toUpperCase();
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return words.map(w => w[0]).join("").slice(0, 3).toUpperCase();
  return name.slice(0, 3).toUpperCase();
}

/**
 * Team logo slot: 6px cut square, --logo-plate backing, 1px --line-strong
 * border, logo contained with 12% padding. Falls back to initials (tag, or
 * first letters of a multi-word name, e.g. Mega Minors -> MM) in JetBrains
 * Mono 700 when there is no logo or it fails to load. `faded` drops a
 * finished match's losing side to 70% opacity.
 */
export default function LogoSlot({ src, name, tag, size, faded = false }: {
  src?: string | null; name: string; tag?: string | null; size: LogoSize; faded?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const [isDark, setIsDark] = useState(() => (src ? darkLogoCache.get(src) ?? false : false));

  useEffect(() => {
    setBroken(false);
    if (!src) return;
    const cached = darkLogoCache.get(src);
    if (cached !== undefined) { setIsDark(cached); return; }
    let alive = true;
    computeIsDark(src).then(v => {
      darkLogoCache.set(src, v);
      if (alive) setIsDark(v);
    });
    return () => { alive = false; };
  }, [src]);

  const fontSize = size <= 20 ? 8 : size <= 34 ? 11 : 16;

  return (
    <span
      className={`logo-slot cut-s${isDark ? " logo-slot-dark" : ""}${faded ? " logo-slot-faded" : ""}`}
      style={{ width: size, height: size }}
    >
      {!src || broken ? (
        <span className="logo-slot-initials num" style={{ fontSize }} aria-hidden="true">
          {initialsFor(name, tag)}
        </span>
      ) : (
        <img
          className="logo-slot-img" src={src} alt="" loading="lazy" decoding="async"
          onError={() => setBroken(true)}
        />
      )}
    </span>
  );
}
