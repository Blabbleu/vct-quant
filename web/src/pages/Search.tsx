import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import LogoSlot from "../components/arena/LogoSlot";
import PlayerPhoto from "../components/arena/PlayerPhoto";
import SectionHead from "../components/arena/SectionHead";
import { EmptyState } from "../components/arena/States";
import { Chip } from "../components/arena/Chip";
import { AnimatePresence, PageFade, m, EASE_OUT, D_FAST, useInitial } from "../lib/motion";
import "./Search.css";

type SearchTeam = { id: number; name: string; tag: string | null; tier: 1 | 2; logo: string | null };
type SearchPlayer = { id: number; handle: string; real_name: string | null; team_id: number | null; team_name: string | null; photo: string | null };
type SearchEvent = { id: number; name: string; tier: 1 | 2 };
type SearchResults = { teams: SearchTeam[]; players: SearchPlayer[]; events: SearchEvent[] };

/**
 * A result row: fades/rises in, fades out when it leaves, and glides (layout, transform only)
 * when rows above it come and go. Rows with `to` are links; event rows are plain.
 */
function SearchRow({ to, index, className = "", children }: { to?: string; index: number; className?: string; children: React.ReactNode }) {
  const init = useInitial("hidden");
  const cls = `search-row${className ? ` ${className}` : ""}`;
  return (
    <m.div
      layout="position"
      initial={init}
      animate="show"
      exit={{ opacity: 0, transition: { duration: D_FAST } }}
      variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
      transition={{ duration: 0.2, ease: EASE_OUT, delay: Math.min(index, 8) * 0.025 }}
      className="search-row-wrap"
    >
      {to ? <Link className={cls} to={to}>{children}</Link> : <div className={cls}>{children}</div>}
    </m.div>
  );
}

const EMPTY: SearchResults = { teams: [], players: [], events: [] };

export default function Search() {
  const [params, setParams] = useSearchParams();
  const [input, setInput] = useState(() => params.get("q") ?? "");
  const [results, setResults] = useState<SearchResults>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [resultsFor, setResultsFor] = useState("");
  const [enterPending, setEnterPending] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const focusRequested = (location.state as { focus?: boolean } | null)?.focus === true;

  useEffect(() => {
    if (focusRequested) inputRef.current?.focus();
  }, [focusRequested, location.key]);

  useEffect(() => {
    const query = params.get("q") ?? "";
    setInput(current => current === query ? current : query);
  }, [params]);

  useEffect(() => {
    const trimmed = input.trim();
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams();
      if (trimmed) next.set("q", input);
      setParams(next, { replace: true });
      if (!trimmed) {
        setResults(EMPTY);
        setResultsFor("");
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
            setResultsFor(trimmed);
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
    setEnterPending(false);
  }

  const total = results.teams.length + results.players.length + results.events.length;
  const firstHref = results.teams[0] ? `/team/${results.teams[0].id}`
    : results.players[0] ? `/player/${results.players[0].id}` : null;
  const current = !loading && !error && resultsFor === input.trim();

  // Enter before results land waits for them, then opens the first linked result.
  useEffect(() => {
    if (!enterPending || !current) return;
    setEnterPending(false);
    if (firstHref) navigate(firstHref);
  }, [enterPending, current, firstHref, navigate]);

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!input.trim()) return;
    if (current && firstHref) navigate(firstHref);
    else setEnterPending(true);
  }

  return (
    <PageFade className="search-page">
      <header className="page-head">
        <h1>Search</h1>
        <p className="lede">Find Tier 1 and Tier 2 teams, players, and events by name, tag, or vlr.gg ID.</p>
      </header>

      <form className="search-form" role="search" onSubmit={onSubmit}>
        <label htmlFor="entity-search">TEAM, PLAYER, EVENT, OR ID</label>
        <div className="search-input-wrap">
          <input
            ref={inputRef}
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
        <span className="search-hint">Search updates as you type; Enter opens the first team or player. Team and player results open recorded profiles; event listings come from official history.</span>
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
              <div className="search-list"><AnimatePresence initial={false} mode="popLayout">
                {results.teams.map((team, i) => (
                  <SearchRow key={`t${team.id}`} index={i} to={`/team/${team.id}`}>
                    <LogoSlot src={team.logo} name={team.name} tag={team.tag} size={34} />
                    <span className="search-primary">{team.name}</span>
                    {team.tag && <span className="search-secondary num">{team.tag}</span>}
                    <Chip variant="ghost">TIER {team.tier}</Chip>
                    <span className="search-row-arrow" aria-hidden="true">→</span>
                  </SearchRow>
                ))}
              </AnimatePresence></div>
            </section>
          )}
          {results.players.length > 0 && (
            <section className="search-section">
              <SectionHead title="Players" right={<span className="num muted small">{results.players.length}</span>} />
              <div className="search-list"><AnimatePresence initial={false} mode="popLayout">
                {results.players.map((player, i) => (
                  <SearchRow key={`p${player.id}`} index={i} to={`/player/${player.id}`}>
                    <PlayerPhoto src={player.photo} handle={player.handle} size={34} />
                    <span className="search-player-name">
                      <span className="search-primary">{player.handle}</span>
                      {player.real_name && <span className="search-secondary">{player.real_name}</span>}
                    </span>
                    {player.team_id
                      ? <span className="search-team"><LogoSlot name={player.team_name ?? "Team"} size={20} /><span>{player.team_name}</span></span>
                      : <span className="search-secondary">Team not recorded</span>}
                    <span className="search-row-arrow" aria-hidden="true">→</span>
                  </SearchRow>
                ))}
              </AnimatePresence></div>
            </section>
          )}
          {results.events.length > 0 && (
            <section className="search-section">
              <SectionHead title="Events" right={<span className="num muted small">{results.events.length}</span>} />
              <div className="search-list"><AnimatePresence initial={false} mode="popLayout">
                {results.events.map((event, i) => (
                  <SearchRow key={`e${event.id}`} index={i} className="search-event">
                    <span className="search-event-mark num">EV</span>
                    <span className="search-primary">{event.name}</span>
                    <Chip variant="ghost">TIER {event.tier}</Chip>
                    <span className="search-secondary num">VLR.GG #{event.id}</span>
                  </SearchRow>
                ))}
              </AnimatePresence></div>
            </section>
          )}
        </div>
      )}
    </PageFade>
  );
}
