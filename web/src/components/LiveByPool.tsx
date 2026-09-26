import type { LiveBucket, LivePool } from "../lib/types";

const pct0 = (v: number | null) => (v == null ? "–" : `${(v * 100).toFixed(0)}%`);

function Range({ b }: { b: LiveBucket }) {
  // A 0-100% track with the 95% interval shaded, the model's mean call as a tick
  // and the observed win rate as a dot: small samples show as wide shading.
  const [lo, hi] = b.ci;
  if (b.n === 0 || lo == null || hi == null || b.predicted == null || b.actual == null) {
    return <span className="muted small">no calls yet</span>;
  }
  return (
    <span className="ci-track" role="img"
      aria-label={`predicted ${pct0(b.predicted)}, won ${pct0(b.actual)}, 95% range ${pct0(lo)} to ${pct0(hi)}`}>
      <i className="ci-band" style={{ left: `${lo * 100}%`, width: `${(hi - lo) * 100}%` }} />
      <i className="ci-pred" style={{ left: `${b.predicted * 100}%` }} />
      <i className="ci-dot" style={{ left: `${b.actual * 100}%` }} />
    </span>
  );
}

/**
 * Graded live forecasts split by rating pool (Game Changers never mixed into
 * Tier 1) with a favourite-folded reliability table. Descriptive only: nothing
 * is fitted to the live log.
 */
export default function LiveByPool({ pools }: { pools: LivePool[] }) {
  if (!pools.length) return null;
  return (
    <section className="panel pad">
      <h2>Live calls by pool</h2>
      <p className="muted small">
        Each forecast is folded to its favourite (30% for one side is a 70% call on the other). Shaded band = 95% range
        for the favourites' true win rate at this sample size; tick = what the model said, dot = what happened.
        A dot inside the band is consistent with good calibration. Game Changers is a separate rating pool.
      </p>
      {pools.map(t => (
        <div key={String(t.tier)} className="pool">
          <h3>{t.label} <span className="muted small">· {t.n} graded</span></h3>
          <div className="kv"><span>Log loss</span><b className="num">{t.log_loss.toFixed(3)}</b></div>
          <div className="kv"><span>Favourite won</span>
            <b className="num">{t.favourite.won} / {t.favourite.calls}</b>
            {t.coin_flips > 0 && <span className="muted small">{t.coin_flips} exact coin flips not counted</span>}</div>
          {t.market && (
            <div className="kv"><span>Liquid market, same matches</span>
              <b className="num">{t.market.market.toFixed(3)}</b>
              <span className="muted small">vs model {t.market.elo.toFixed(3)} · n={t.market.n} · lower is better</span></div>
          )}
          <div className="scroll"><table className="reliability">
            <thead><tr><th>Called at</th><th className="n">n</th><th className="n">Said</th><th className="n">Won</th><th>95% range</th></tr></thead>
            <tbody>{t.buckets.map(b => (
              <tr key={b.lo} className={b.n ? "" : "muted"}>
                <td className="num">{(b.lo * 100).toFixed(0)}–{(b.hi * 100).toFixed(0)}%</td>
                <td className="n">{b.n}</td>
                <td className="n">{pct0(b.predicted)}</td>
                <td className="n">{b.n ? `${b.won}/${b.n}` : "–"}</td>
                <td className="ci-cell"><Range b={b} /></td>
              </tr>
            ))}</tbody>
          </table></div>
        </div>
      ))}
    </section>
  );
}
