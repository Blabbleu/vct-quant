import { useState } from "react";

export default function PlayerPhoto({ src, handle, size = 40 }: { src: string | null; handle: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const initials = handle.trim().slice(0, 2).toUpperCase() || "?";
  return (
    <span className="player-photo" style={{ width: size, height: size }} aria-label={`${handle} photo`}>
      {src && !failed
        ? <img src={src} alt="" width={size} height={size} loading="lazy" onError={() => setFailed(true)} />
        : <span aria-hidden="true">{initials}</span>}
    </span>
  );
}
