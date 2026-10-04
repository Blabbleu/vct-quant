import { useEffect, useRef, useState } from "react";
import { useOps } from "../lib/api";
import type { OpsRun, OpsSource } from "../lib/types";
import SectionHead from "../components/arena/SectionHead";
import StatCell from "../components/arena/StatCell";
import Panel from "../components/arena/Panel";
import { Chip } from "../components/arena/Chip";
import { LoadingBlocks, ErrorPanel } from "../components/arena/States";
import { PageFade } from "../lib/motion";
import "./Status.css";

const utc = (iso: string | null) => iso == null ? "\u2013" : new Date(iso).toLocaleString(undefined, {
  timeZone: "UTC", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
}) + " UTC";

const age = (hours: number | null) => hours == null ? "never"
  : hours < 1 ? `${Math.round(hours * 60)}m ago`
  : hours < 48 ? `${hours.toFixed(1)}h ago` : `${Math.round(hours / 24)}d ago`;

const STATUS_TEXT: Record<string, string> = {
  ok: "Refreshing normally",
  degraded: "Last refresh did not complete; forecasts are from an earlier refresh",
  stale: "No successful refresh recently; forecasts may be out of date",
  unknown: "No matchday log on this server",
};

const SOURCE_LABEL: Record<string, string> = {
  events: "vlr.gg event list",
  event_matches: "vlr.gg event matches",
  upcoming: "vlr.gg upcoming fixtures",
  match_details: "vlr.gg match details",
  polymarket: "Polymarket prices",
};

/** Status-board dot: OK is model-coloured, degraded states neutral, stale/failed reads as market-gold. */
function Dot({ outcome }: { outcome: string }) {
  const cls = outcome === "ok" ? "status-dot-ok"
    : outcome === "stale" || outcome === "failed" ? "status-dot-bad"
    : "status-dot-mid";
  return <span className={`status-dot ${cls}`} aria-hidden="true" />;
}

function Run({ r }: { r: OpsRun }) {
  return (
    <div className="status-run">
      <Dot outcome={r.outcome} />
      <div className="status-run-body">
        <div className="status-run-head">
          <span className="num status-run-time">{utc(r.started_at)}</span>
          <Chip variant={r.outcome === "ok" ? "default" : "ghost"}>{r.outcome.toUpperCase()}</Chip>
        </div>
        {r.outcome === "ok" && (
          <div className="muted small">{r.upcoming_retained} official fixtures from {r.upcoming_fetched} upcoming
            {r.graded_n != null ? ` \u00b7 ${r.graded_n} forecasts graded` : ""}</div>
        )}
        {r.reason && <div className="muted small">{r.reason}</div>}
        {r.warnings.map(w => <div key={w} className="status-warning">{w}</div>)}
      </div>
    </div>
  );
}

function Source({ name, s }: { name: string; s: OpsSource }) {
  return (
    <div className="status-kv">
      <span>{SOURCE_LABEL[name] ?? name}</span>
      <span className="num status-kv-age">{age(s.age_hours)}</span>
      <span className="muted small">{s.fetched_at ? `${utc(s.fetched_at)} \u00b7 ${s.files.toLocaleString()} snapshots kept` : "no snapshot"}</span>
    </div>
  );
}

/** Owner-only ops panel restyled as a terminal status board: dots, mono timestamps, dense rows. */
export default function Status() {
  const [nonce, setNonce] = useState(0);
  const { data, error, loading } = useOps(nonce);
  const [lastGood, setLastGood] = useState<typeof data>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const wasLoading = useRef(true);

  useEffect(() => {
    if (data) setLastGood(data);
  }, [data]);
  useEffect(() => {
    if (loading) {
      wasLoading.current = true;
    } else if (wasLoading.current) {
      wasLoading.current = false;
      setCheckedAt(new Date());
    }
  }, [loading]);

  const visibleData = data ?? lastGood;
  if (loading && !visibleData) return <div className="status-page"><LoadingBlocks label="Loading status\u2026" /></div>;
  if (!visibleData) return <div className="status-page"><ErrorPanel detail={error ?? "no data"} onRetry={() => setNonce(n => n + 1)} /></div>;
  const md = visibleData.matchday;
  const counts = Object.entries(md.last_24h).map(([k, v]) => `${v} ${k}`).join(" \u00b7 ") || "none";

  return (
    <PageFade className="status-page">
      <header className="status-head">
        <h1 className="status-title">Data status</h1>
        <p className="status-lede">How fresh the data behind the forecasts is. Fixtures and results refresh from vlr.gg every two hours; market prices are fetched in the same run. Read from local files only: opening this page never calls vlr.gg or Polymarket.</p>
      </header>

      <Panel cut="l" frame="line">
        <div className="pad status-banner">
          <Dot outcome={md.status} />
          <b className="status-banner-text">{STATUS_TEXT[md.status] ?? md.status}</b>
          <button type="button" className="btn btn-secondary" onClick={() => setNonce(n => n + 1)} disabled={loading}>
            {loading ? "Checking…" : "Recheck"}
          </button>
          {checkedAt && <span className="muted small status-checked" role="status">Checked {checkedAt.toLocaleTimeString(undefined, { timeZone: "UTC", hour12: false })} UTC</span>}
        </div>
      </Panel>
      {error && <p className="status-error" role="alert">Recheck failed: {error}. Showing the last successful status.</p>}
      <p className="muted small">
        Last successful refresh {md.last_success ? `${utc(md.last_success.started_at)} (${age(md.last_success_age_hours)})` : "none on record"}.
        Stale after {md.stale_hours}h without one. Last 24h: {counts}.
      </p>

      <div className="status-cells">
        <StatCell label="Upcoming fixtures with a forecast" value={visibleData.prediction_log.upcoming_matches} />
        <StatCell label="Last forecast logged" value={age(visibleData.prediction_log.age_hours)} />
        <StatCell label="Next scheduled match" value={visibleData.prediction_log.next_scheduled_at ? utc(visibleData.prediction_log.next_scheduled_at) : "\u2013"} />
        <StatCell label="Newest completed match" value={visibleData.database.latest_completed_on ?? "\u2013"} />
      </div>

      <Panel cut="l" frame="line">
        <div className="pad">
          <SectionHead title="Sources" />
          <div className="status-sources">
            {Object.entries(visibleData.sources).map(([name, s]) => <Source key={name} name={name} s={s} />)}
            <div className="status-kv">
              <span>Database file</span>
              <span className="num status-kv-age">{age(visibleData.database.age_hours)}</span>
              <span className="muted small">{visibleData.database.matches != null ? `${visibleData.database.matches.toLocaleString()} matches \u00b7 ` : ""}
                newest source observation {utc(visibleData.database.latest_seen_at)}</span>
            </div>
          </div>
          <p className="muted small">Fetch times come from the raw snapshot filenames. A source only refetches when the refresh reaches it, so match details age until a new team needs resolving.</p>
        </div>
      </Panel>

      <Panel cut="l" frame="line">
        <div className="pad">
          <SectionHead title="Recent refreshes" />
          {md.recent_runs.length === 0 && <p className="muted">No runs logged.</p>}
          <div className="status-runs">
            {md.recent_runs.map(r => <Run key={r.started_at} r={r} />)}
          </div>
        </div>
      </Panel>

      <p className="muted small">Page generated {utc(visibleData.generated_at)}.</p>
    </PageFade>
  );
}
