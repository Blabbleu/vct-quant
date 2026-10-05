import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import LogoSlot from "./arena/LogoSlot";
import PlayerPhoto from "./arena/PlayerPhoto";
import SectionHead from "./arena/SectionHead";
import { EmptyState } from "./arena/States";
import { Chip } from "./arena/Chip";
import { AnimatePresence, m, EASE_OUT, D_FAST, useInitial } from "../lib/motion";
import { linkTargets, moveActive } from "../lib/searchModel";
import { useSearch } from "../lib/useSearch";
import "../pages/Search.css";

/**
 * A result row: fades/rises in, fades out when it leaves, and glides (layout, transform only)
 * when rows above it come and go. Rows with `to` are links; event rows are plain.
 */
function SearchRow({ to, index, className = "", active, id, replace, onHover, children }: {
  to?: string; index: number; className?: string; active?: boolean; id?: string; replace?: boolean;
  onHover?: () => void; children: React.ReactNode;
}) {
  const init = useInitial("hidden");
  const cls = `search-row${className ? ` ${className}` : ""}${active ? " is-active" : ""}`;
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
      {to
        ? <Link id={id} className={cls} to={to} replace={replace} role="option" aria-selected={!!active} tabIndex={-1} onMouseMove={onHover}>{children}</Link>
        : <div className={cls}>{children}</div>}
    </m.div>
  );
}

/**
 * The whole search experience (input, keyboard handling, grouped results, states). The /search page and the
 * overlay both render this; `replaceOnOpen` makes a selection replace the current history entry (overlay).
 */
export default function SearchPanel({ query, onQueryChange, autoFocus = false, replaceOnOpen = false, inputRef, headExtra, variant }: {
  query: string;
  onQueryChange: (q: string) => void;
  autoFocus?: boolean;
  replaceOnOpen?: boolean;
  inputRef?: React.RefObject<HTMLInputElement | null>;
  headExtra?: React.ReactNode;
  variant: "page" | "overlay";
}) {
  const { results, loading, error, current, retry } = useSearch(query);
  const navigate = useNavigate();
  const own = useRef<HTMLInputElement>(null);
  const field = inputRef ?? own;
  const [active, setActive] = useState(0);
  const [enterPending, setEnterPending] = useState(false);
  const uid = useId().replace(/:/g, "");
  const listId = `${uid}-results`;

  const targets = useMemo(() => linkTargets(results), [results]);
  const total = results.teams.length + results.players.length + results.events.length;
  const rowId = (key: string) => `${uid}-${key}`;
  const activeTarget = current ? targets[active] : undefined;

  useEffect(() => { if (autoFocus) field.current?.focus(); }, [autoFocus, field]);
  useEffect(() => { setActive(0); }, [results]);

  // Keep the active row visible inside the scrolling results list.
  useEffect(() => {
    if (activeTarget) document.getElementById(rowId(activeTarget.key))?.scrollIntoView({ block: "nearest" });
  }, [activeTarget?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  // Enter before results land waits for them, then opens the active (first) result.
  useEffect(() => {
    if (!enterPending || !current) return;
    setEnterPending(false);
    if (targets[0]) navigate(targets[0].href, { replace: replaceOnOpen });
  }, [enterPending, current, targets, navigate, replaceOnOpen]);

  function change(value: string) { onQueryChange(value); setEnterPending(false); }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!current || targets.length === 0) return;
      e.preventDefault();
      setActive(a => moveActive(a, e.key === "ArrowDown" ? 1 : -1, targets.length));
    }
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    if (current && targets.length) navigate((targets[active] ?? targets[0]).href, { replace: replaceOnOpen });
    else setEnterPending(true);
  }

  const hover = (key: string) => () => { const i = targets.findIndex(t => t.key === key); if (i >= 0) setActive(i); };

  return (
    <div className={`search-panel search-panel-${variant}`}>
      <form className="search-form" role="search" onSubmit={onSubmit} onKeyDown={onKeyDown}>
        <div className="search-form-head">
          <label htmlFor={`${uid}-input`}>TEAM, PLAYER, EVENT, OR ID</label>
          {headExtra}
        </div>
        <div className="search-input-wrap">
          <input
            ref={field}
            id={`${uid}-input`}
            type="search"
            role="combobox"
            aria-expanded={current && targets.length > 0}
            aria-controls={listId}
            aria-activedescendant={activeTarget ? rowId(activeTarget.key) : undefined}
            aria-autocomplete="list"
            value={query}
            maxLength={100}
            autoComplete="off"
            enterKeyHint="search"
            placeholder="e.g. Paper Rex, aspas, Champions"
            onChange={event => change(event.target.value)}
          />
          {query && <button type="button" className="search-clear" onClick={() => { change(""); field.current?.focus(); }} aria-label="Clear search">Clear</button>}
        </div>
        <span className="search-hint">
          {variant === "overlay"
            ? "↑↓ to move, Enter opens the highlighted team or player, Esc closes."
            : "Search updates as you type; Enter opens the first team or player. Team and player results open recorded profiles; event listings come from official history."}
        </span>
      </form>

      <div className="search-body" id={listId} role="listbox" aria-label="Search results">
        {!query.trim() ? (
          <EmptyState title="START SEARCHING" line="Enter a team, player, event, or numeric ID. Search is limited to official Tier 1 and Tier 2 history." />
        ) : loading ? (
          <p className="search-status num" role="status">SEARCHING…</p>
        ) : error ? (
          <div className="search-error" role="alert">
            <p>{error}</p>
            <button type="button" className="btn btn-secondary" onClick={retry}>Retry</button>
          </div>
        ) : total === 0 ? (
          <EmptyState title="NO MATCHES" line={`No teams, players, or events matched “${query.trim()}”. Try a tag, shorter name, or ID.`} />
        ) : (
          <div className="search-results" aria-live="polite">
            <p className="search-count num">{total} RESULT{total === 1 ? "" : "S"} · UP TO 20 PER CATEGORY</p>
            {results.teams.length > 0 && (
              <section className="search-section">
                <SectionHead title="Teams" right={<span className="num muted small">{results.teams.length}</span>} />
                <div className="search-list"><AnimatePresence initial={false} mode="popLayout">
                  {results.teams.map((team, i) => (
                    <SearchRow key={`t${team.id}`} index={i} to={`/team/${team.id}`} id={rowId(`t${team.id}`)} replace={replaceOnOpen}
                      active={activeTarget?.key === `t${team.id}`} onHover={hover(`t${team.id}`)}>
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
                    <SearchRow key={`p${player.id}`} index={i} to={`/player/${player.id}`} id={rowId(`p${player.id}`)} replace={replaceOnOpen}
                      active={activeTarget?.key === `p${player.id}`} onHover={hover(`p${player.id}`)}>
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
      </div>
    </div>
  );
}
