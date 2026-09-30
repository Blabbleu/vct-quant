import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import LogoSlot from "../components/arena/LogoSlot";
import PlayerPhoto from "../components/arena/PlayerPhoto";
import SectionHead from "../components/arena/SectionHead";
import { EmptyState } from "../components/arena/States";
import { Chip } from "../components/arena/Chip";
import "./Search.css";

type SearchTeam = { id: number; name: string; tag: string | null; tier: 1 | 2; logo: string | null };
type SearchPlayer = { id: number; handle: string; real_name: string | null; team_id: number | null; team_name: string | null; photo: string | null };
type SearchEvent = { id: number; name: string; tier: 1 | 2 };
type SearchResults = { teams: SearchTeam[]; players: SearchPlayer[]; events: SearchEvent[] };

const EMPTY: SearchResults = { teams: [], players: [], events: [] };

export default function Search() {
  const [params, setParams] = useSearchParams();
  const [input, setInput] = useState(() => params.get("q") ?? "");
  const [results, setResults] = useState<SearchResults>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const trimmed = input.trim();
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams();
      if (trimmed) next.set("q", input);
      setParams(next, { replace: true });
      if (!trimmed) {
        setResults(EMPTY);
        setError(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      fetch(`/api/search?q=${encodeURIComponent(trimmed)}&limit=20`, { signal: controller.signal })
        .then(async response => {
          if (!response.ok) throw new Error(response.status === 503
            ? "Search is temporarily unavailable. Try again shortly."
            : `Search failed (${response.status}).`);
          return response.json() as Promise<SearchResults>;
        })
        .then(data => {
          if (Array.isArray(data.teams) && Array.isArray(data.players) && Array.isArray(data.events)) {
            setResults(data);
          } else {
            throw new Error("Search returned an unexpected response.");
          }
        })
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") return;
          setError(reason instanceof Error ? reason.message : "Search failed.");
          setResults(EMPTY);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 220);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [input, retry, setParams]);

  function changeQuery(value: string) {
    setInput(value);
  }

  const total = results.teams.length + results.players.length + results.events.length;

  return (
    <div className="search-page">
      <header className="page-head">
        <h1>Search</h1>
        <p className="lede">Find Tier 1 and Tier 2 teams, players, and events by name, tag, or vlr.gg ID.</p>
      </header>

      <form className="search-form" role="search" onSubmit={event => event.preventDefault()}>
        <label htmlFor="entity-search">TEAM, PLAYER, EVENT, OR ID</label>
        <div className="search-input-wrap">
          <input
            id="entity-search"
            type="search"
            value={input}
            maxLength={100}
            autoComplete="off"
            placeholder="e.g. Paper Rex, aspas, Champions"
            onChange={event => changeQuery(event.target.value)}
          />
          {input && <button type="button" className="search-clear" onClick={() => changeQuery("")} aria-label="Clear search">Clear</button>}
        </div>
        <span className="search-hint">Search updates as you type. Team and player results open recorded profiles; event listings come from official history.</span>
      </form>

      {!input.trim() ? (
        <EmptyState title="START SEARCHING" line="Enter a team, player, event, or numeric ID. Search is limited to official Tier 1 and Tier 2 history." />
      ) : loading ? (
        <p className="search-status num" role="status">SEARCHING…</p>
      ) : error ? (
        <div className="search-error" role="alert">
          <p>{error}</p>
          <button type="button" className="btn btn-secondary" onClick={() => setRetry(value => value + 1)}>Retry</button>
        </div>
      ) : total === 0 ? (
        <EmptyState title="NO MATCHES" line={`No teams, players, or events matched “${input.trim()}”. Try a tag, shorter name, or ID.`} />
      ) : (
        <div className="search-results" aria-live="polite">
          <p className="search-count num">{total} RESULT{total === 1 ? "" : "S"} · UP TO 20 PER CATEGORY</p>
          {results.teams.length > 0 && (
            <section className="search-section">
              <SectionHead title="Teams" right={<span className="num muted small">{results.teams.length}</span>} />
              <div className="search-list">
                {results.teams.map(team => (
                  <Link className="search-row" to={`/team/${team.id}`} key={team.id}>
                    <LogoSlot src={team.logo} name={team.name} tag={team.tag} size={34} />
                    <span className="search-primary">{team.name}</span>
                    {team.tag && <span className="search-secondary num">{team.tag}</span>}
                    <Chip variant="ghost">TIER {team.tier}</Chip>
                    <span className="search-row-arrow" aria-hidden="true">→</span>
                  </Link>
                ))}
              </div>
            </section>
          )}
          {results.players.length > 0 && (
            <section className="search-section">
              <SectionHead title="Players" right={<span className="num muted small">{results.players.length}</span>} />
              <div className="search-list">
                {results.players.map(player => (
                  <Link className="search-row" to={`/player/${player.id}`} key={player.id}>
                    <PlayerPhoto src={player.photo} handle={player.handle} size={34} />
                    <span className="search-player-name">
                      <span className="search-primary">{player.handle}</span>
                      {player.real_name && <span className="search-secondary">{player.real_name}</span>}
                    </span>
                    {player.team_id
                      ? <span className="search-team"><LogoSlot name={player.team_name ?? "Team"} size={20} /><span>{player.team_name}</span></span>
                      : <span className="search-secondary">Team not recorded</span>}
                    <span className="search-row-arrow" aria-hidden="true">→</span>
                  </Link>
                ))}
              </div>
            </section>
          )}
          {results.events.length > 0 && (
            <section className="search-section">
              <SectionHead title="Events" right={<span className="num muted small">{results.events.length}</span>} />
              <div className="search-list">
                {results.events.map(event => (
                  <div className="search-row search-event" key={event.id}>
                    <span className="search-event-mark num">EV</span>
                    <span className="search-primary">{event.name}</span>
                    <Chip variant="ghost">TIER {event.tier}</Chip>
                    <span className="search-secondary num">VLR.GG #{event.id}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
