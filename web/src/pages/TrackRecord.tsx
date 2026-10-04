import { Link } from "react-router-dom";
import { useSnapshot } from "../lib/api";
import { logLoss, pct } from "../lib/format";
import Calibration from "../components/Calibration";
import CheckpointPanel, { fmtT, MIN_T_N } from "../components/CheckpointPanel";
import LiveByPool from "../components/LiveByPool";
import LogoSlot from "../components/arena/LogoSlot";
import TeamLabel from "../components/arena/TeamLabel";
import SectionHead from "../components/arena/SectionHead";
import StatCell from "../components/arena/StatCell";
import { Chip } from "../components/arena/Chip";
import Panel from "../components/arena/Panel";
import { LoadingBlocks, ErrorPanel } from "../components/arena/States";
import { PageFade } from "../lib/motion";
import "./TrackRecord.css";

const SHADOW_NAMES: Record<string, string> = {
  ensemble: "Fast/slow ensemble", shrink: "Online shrink", "carry-over": "Roster carry-over",
};

export default function TrackRecord() {
  const { data, error, loading } = useSnapshot();
  if (loading) return <div className="record-page"><LoadingBlocks label="Loading track record\u2026" /></div>;
  if (error || !data) return <div className="record-page"><ErrorPanel detail={error ?? "no data"} onRetry={() => location.reload()} /></div>;
  const { live, backtest, ledger } = data;

  return (
    <PageFade className="record-page">
      <header className="record-head">
        <h1 className="record-title">Track record</h1>
        <p className="record-lede">Every forecast is saved before the match starts and graded after. Log loss rewards being confidently right and punishes being confidently wrong; a coin flip scores 0.693, lower is better.</p>
      </header>

      <div className="record-scorecard">
        <StatCell label="Live log loss" value={live.log_loss != null ? live.log_loss.toFixed(3) : "\u2013"} tone="model" />
        <StatCell label="Coin flip" value="0.693" />
        <StatCell label="Backtest log loss" value={backtest.log_loss.toFixed(3)} />
        <StatCell label="Backtest picks winner" value={pct(backtest.accuracy)} tone="result" />
      </div>
      <p className="record-scorecard-note">Live: {live.graded} graded forecasts. Backtest: {backtest.n.toLocaleString()} past matches, held out by fold.</p>

      {live.by_tier && (
        <Panel cut="l" frame="line">
          <div className="pad"><LiveByPool pools={live.by_tier.tiers} /></div>
        </Panel>
      )}

      <div className="record-grid">
        <Panel cut="l" frame="line" className="record-panel">
          <div className="pad record-panel-in">
            <SectionHead title="Calibration" />
            <Calibration buckets={backtest.calibration} />
            <p className="muted small">Points on the dashed line are well calibrated. Below the line means overconfident. Point size scales with sample size.</p>
          </div>
        </Panel>
        <Panel cut="l" frame="line" className="record-panel">
          <div className="pad record-panel-in">
            <SectionHead title="Models in testing" />
            <p className="muted small">Shadow models run alongside but never decide the forecast until they beat it on enough matches.
              Paired t is shown from n &ge; {MIN_T_N}; positive means the shadow is ahead.</p>
            <div className="record-shadows">
              {Object.entries(live.shadows).map(([k, s]) => (
                <div className="record-shadow-row" key={k}>
                  <span className="record-shadow-name">{SHADOW_NAMES[k] ?? k}</span>
                  <span className="num record-shadow-score">{s.shadow.toFixed(3)}</span>
                  <span className="muted small">vs Elo {s.elo.toFixed(3)} &middot; n={s.n} &middot; t {fmtT(s.t, s.n)}</span>
                </div>
              ))}
            </div>
          </div>
        </Panel>
      </div>

      {live.checkpoint && (
        <Panel cut="l" frame="line">
          <div className="pad"><CheckpointPanel cp={live.checkpoint} /></div>
        </Panel>
      )}

      <Panel cut="l" frame="line">
        <div className="pad">
          <SectionHead title="Every graded call" right={<span className="muted small">{live.logged} logged &middot; {live.graded} finished</span>} />
          <div className="scroll">
            <table className="record-table">
              <thead>
                <tr><th>Match</th><th className="n">Model</th><th className="n">Market</th><th className="n">Log loss</th><th>Call</th></tr>
              </thead>
              <tbody>
                {[...live.rows].reverse().map(r => (
                  <tr key={r.match_id}>
                    <td>
                      <Link to={`/match/${r.match_id}`} className="record-table-match">
                        <LogoSlot src={r.logo_a} name={r.team_a} tag={r.tag_a} size={20} />
                        <TeamLabel name={r.team_a} tag={r.tag_a} mode="auto" />
                        <span className="vs">vs</span>
                        <LogoSlot src={r.logo_b} name={r.team_b} tag={r.tag_b} size={20} />
                        <TeamLabel name={r.team_b} tag={r.tag_b} mode="auto" />
                      </Link>
                    </td>
                    <td className="num n">{pct(r.p)}</td>
                    <td className="num n">{pct(r.market)}</td>
                    <td className="num n">{logLoss(r.p, r.won).toFixed(3)}</td>
                    <td><Chip variant={r.won ? "result" : "ghost"}>{r.won ? "HIT" : "MISS"}</Chip></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Panel>

      <Panel cut="l" frame="line">
        <div className="pad">
          <SectionHead title="Experiment ledger" right={<span className="muted small">every idea tested, including failures</span>} />
          <div className="scroll">
            <table className="record-table">
              <thead><tr><th>Variant</th><th>Tested on</th><th className="n">Score</th><th>Verdict</th></tr></thead>
              <tbody>
                {ledger.map(r => (
                  <tr key={r.name}>
                    <td>{r.name}</td>
                    <td className="muted">{r.holdout}</td>
                    <td className="num n">{r.score}</td>
                    <td><span className={`verdict ${r.verdict.replace(/\s+/g, "-")}`}>{r.verdict}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Panel>
    </PageFade>
  );
}
