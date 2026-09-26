export type BannerKind = "complete" | "live" | "upcoming";

/** MATCH COMPLETE / LIVE / kick-off banner. Live gets a pulsing --market dot (static under reduced motion via CSS). */
export default function Banner({ kind, text }: { kind: BannerKind; text: string }) {
  return (
    <div className={`banner-arena banner-arena-${kind}`}>
      {kind === "live" && <span className="live-dot" aria-hidden="true" />}
      <span>{text}</span>
    </div>
  );
}
