import { Link } from "react-router-dom";
import type { Checkpoint } from "../lib/types";

/** Paired t over fewer matches than this is shown as a dash: it says nothing. */
export const MIN_T_N = 10;

export const fmtT = (t: number | null | undefined, n: number) =>
  t == null || !Number.isFinite(t) || n < MIN_T_N ? "–" : `${t >= 0 ? "+" : ""}${t.toFixed(2)}`;

const VERDICT: Record<Checkpoint["checkpoint_1"]["verdict"], string> = {
  too_few: "Not enough graded matches yet",
  no_worse: "Currently no worse than Elo",
  boundary: "Tied to 4 decimals: owner decides",
  worse: "Currently worse than Elo",
};

/**
 * Where the fast/slow ensemble stands against the promotion rule fixed on
 * 2026-09-24 (docs/model-lab-2026-09-24.md section 3). Descriptive only: this
 * panel never promotes anything, and the rule is not retuned on live results.
 */
export default function CheckpointPanel({ cp }: { cp: Checkpoint }) {
  const c1 = cp.checkpoint_1;
  const diff = c1.diff == null ? "–" : `${c1.diff > 0 ? "+" : ""}${c1.diff.toFixed(4)}`;
  const progress = Math.min(1, c1.n / cp.min_n);
  return (
    <div className="panel pad checkpoint">
      <h2>Promotion checkpoint</h2>
      <p className="muted small">
        Rule fixed before any live grading: after the Champions 2026{" "}
        <Link to={`/match/${cp.final_match_id}`}>grand final</Link> is graded, the fast/slow ensemble replaces Elo
        only if n ≥ {cp.min_n} and its log loss is no worse. Scores below are same-match comparisons.
      </p>
      <div className="kv"><span>Checkpoint 1</span>
        <b className="num">{c1.state === "final_graded" ? "final graded" : "waiting for final"}</b></div>
      <div className="kv"><span>Graded with ensemble</span><b className="num">{c1.n} / {cp.min_n}</b></div>
      <div className="progress" role="img" aria-label={`${c1.n} of ${cp.min_n} matches`}>
        <i style={{ width: `${(progress * 100).toFixed(0)}%` }} />
      </div>
      <div className="kv"><span>Ensemble − Elo log loss</span><b className="num">{diff}</b>
        <span className="muted small">negative = ensemble better · paired t {fmtT(c1.t, c1.n)}</span></div>
      <div className="kv"><span>Reading</span>
        <b className={`verdict ${c1.verdict === "worse" ? "rejected" : "shadow"}`}>{VERDICT[c1.verdict]}</b></div>
      <div className="kv"><span>Checkpoint 2</span>
        <b className="num">{cp.checkpoint_2.n} / {cp.checkpoint_2_n}</b></div>
      <p className="muted small">
        {c1.state === "awaiting_final"
          ? "A running score, not a verdict: nothing is decided until the final is graded."
          : "Checkpoint 1 is frozen at the final; later matches count toward checkpoint 2 only."}{" "}
        Promotion changes the published forecast and needs the owner's approval.
      </p>
    </div>
  );
}
