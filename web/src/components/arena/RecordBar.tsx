/**
 * CALLS segmented bar (hits of calls filled) plus one Meta line comparing
 * log loss to a coin flip (ln 2 ~= 0.693) and, when known, the market.
 */
export default function RecordBar({ calls, hits, logLoss, coin = 0.693, market }: {
  calls: number; hits: number; logLoss: number; coin?: number; market?: number | null;
}) {
  return (
    <div className="record-bar">
      <div className="record-bar-label">
        <span>CALLS</span>
        <span className="num">{hits} / {calls}</span>
      </div>
      <div className="record-bar-track" role="img" aria-label={`${hits} of ${calls} calls right`}>
        {Array.from({ length: calls }, (_, i) => (
          <span key={i} className={`record-bar-seg${i < hits ? " record-bar-seg-filled" : ""}`} />
        ))}
      </div>
      <p className="record-bar-meta num">
        Log loss {logLoss.toFixed(3)} vs coin flip {coin.toFixed(3)}
        {market != null ? ` vs market ${market.toFixed(3)}` : ""}
      </p>
    </div>
  );
}
