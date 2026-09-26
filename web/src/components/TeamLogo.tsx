import { useState } from "react";

/** Team logo with a lettered fallback when there is no logo or it fails to load. */
export default function TeamLogo({ src, name, size = 24 }: { src?: string | null; name: string; size?: number }) {
  const [broken, setBroken] = useState(false);
  const style = { width: size, height: size };
  if (!src || broken) {
    const letters = name.replace(/[^\p{L}\p{N} ]/gu, "").split(/\s+/).filter(Boolean)
      .slice(0, 2).map(w => w[0]).join("").toUpperCase() || "?";
    return <span className="logo fallback" style={{ ...style, fontSize: Math.round(size * 0.4) }} aria-hidden>{letters}</span>;
  }
  return <img className="logo" src={src} alt="" style={style} loading="lazy" decoding="async"
    onError={() => setBroken(true)} />;
}
