import { useState } from "react";
import { useOps } from "../lib/api";
import type { OpsRun, OpsSource } from "../lib/types";
import { int } from "../lib/format";
import { Failure, Loading, PageHead, Tile } from "../components/ui";

const utc = (iso: string | null) => iso == null ? "–" : new Date(iso).toLocaleString(undefined, {
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

function Run({ r }: { r: OpsRun }) {
  return (
    <div className="ops-run">
      <span className={`ops-dot ${r.outcome}`} aria-hidden="true" />
      <div>
        <div className="head"><b className="num small">{utc(r.started_at)}</b><span className="chip">{r.outcome}</span></div>
        {r.outcome === "ok" && (
          <div className="muted small">{r.upcoming_retained} official fixtures from {r.upcoming_fetched} upcoming
            {r.graded_n != null ? ` · ${r.graded_n} forecasts graded` : ""}</div>
        )}
        {r.reason && <div className="muted small">{r.reason}</div>}
        {r.warnings.map(w => <div key={w} className="champions-warning">{w}</div>)}
      </div>
    </div>
  );
}

function Source({ name, s }: { name: string; s: OpsSource }) {
  return (
    <div className="kv">
      <span>{SOURCE_LABEL[name] ?? name}</span>
      <b className="num small">{age(s.age_hours)}</b>
      <span className="muted small">{s.fetched_at ? `${utc(s.fetched_at)} · ${int(s.files)} snapshots kept` : "no snapshot"}</span>
    </div>
  );
}

export default function Status() {
  const [nonce, setNonce] = useState(0);
  const { data, error, loading } = useOps(nonce);
  if (loading && !data) return <Loading what="status" />;
  if (error || !data) return <Failure error={error ?? "no data"} />;
  const md = data.matchday;
  const counts = Object.entries(md.last_24h).map(([k, v]) => `${v} ${k}`).join(" · ") || "none";
  return (
    <>
      <PageHead eyebrow="Ops" title="Data status">
        How fresh the data behind the forecasts is. Fixtures and results refresh from vlr.gg every two hours; market prices
        are fetched in the same run. Read from local files only: opening this page never calls vlr.gg or Polymarket.
      </PageHead>
      <section className="panel pad">
        <div className="ops-status">
          <span className={`ops-dot ${md.status}`} aria-hidden="true" />
          <b>{STATUS_TEXT[md.status] ?? md.status}</b>
          <button className="chip" onClick={() => setNonce(n => n + 1)}>Recheck</button>
        </div>
        <div className="muted small">
          Last successful refresh {md.last_success ? `${utc(md.last_success.started_at)} (${age(md.last_success_age_hours)})` : "none on record"}.
          Stale after {md.stale_hours}h without one. Last 24h: {counts}.
        </div>
      </section>
      <div className="tiles">
        <Tile value={data.prediction_log.upcoming_matches} label="upcoming fixtures with a forecast" />
        <Tile value={age(data.prediction_log.age_hours)} label="last forecast logged" />
        <Tile value={data.prediction_log.next_scheduled_at ? utc(data.prediction_log.next_scheduled_at) : "–"} label="next scheduled match" />
        <Tile value={data.database.latest_completed_on ?? "–"} label="newest completed match in the database" />
      </div>
      <section className="panel pad">
        <h2>Sources</h2>
        {Object.entries(data.sources).map(([name, s]) => <Source key={name} name={name} s={s} />)}
        <div className="kv">
          <span>Database file</span>
          <b className="num small">{age(data.database.age_hours)}</b>
          <span className="muted small">{data.database.matches != null ? `${int(data.database.matches)} matches · ` : ""}
            newest source observation {utc(data.database.latest_seen_at)}</span>
        </div>
        <p className="muted small">Fetch times come from the raw snapshot filenames. A source only refetches when the
          refresh reaches it, so match details age until a new team needs resolving.</p>
      </section>
      <section className="panel pad">
        <h2>Recent refreshes</h2>
        {md.recent_runs.length === 0 && <p className="muted">No runs logged.</p>}
        {md.recent_runs.map(r => <Run key={r.started_at} r={r} />)}
      </section>
      <p className="muted small">Page generated {utc(data.generated_at)}.</p>
    </>
  );
}
