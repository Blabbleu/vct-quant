import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import SearchPanel from "./SearchPanel";
import { AnimatePresence, m, EASE_OUT, D_FAST } from "../lib/motion";
import { useReducedMotion } from "motion/react";
import { overlayOpen, withOverlay, withoutOverlay } from "../lib/searchModel";
import "./SearchOverlay.css";

/**
 * Search as an overlay over the current page. Open state lives in history state (one pushed entry that
 * carries a flag): Back pops it and closes the overlay without leaving the page, picking a result
 * replaces it (so Back from the destination returns to the page that was underneath), and any route
 * change drops the flag, closing it.
 */
export function useSearchOverlay() {
  const location = useLocation();
  const navigate = useNavigate();
  const open = overlayOpen(location.state);
  const pushed = useRef(false);
  const returnTo = useRef<HTMLElement | null>(null);

  useEffect(() => { if (!open) pushed.current = false; }, [open]);

  const openOverlay = useCallback(() => {
    if (open) return;
    const el = document.activeElement as HTMLElement | null;
    returnTo.current = el && el !== document.body ? el : document.querySelector<HTMLElement>(".nav-search");
    pushed.current = true;
    navigate({ pathname: location.pathname, search: location.search, hash: location.hash }, { state: withOverlay(location.state) });
  }, [open, navigate, location]);

  const close = useCallback(() => {
    if (!open) return;
    if (pushed.current) navigate(-1);
    else navigate({ pathname: location.pathname, search: location.search, hash: location.hash }, { replace: true, state: withoutOverlay(location.state) });
  }, [open, navigate, location]);

  return { open, openOverlay, close, returnTo };
}

const FOCUSABLE = "input:not([disabled]), button:not([disabled]), a[href]:not([tabindex='-1']), [tabindex]:not([tabindex='-1'])";

function Dialog({ onClose, returnTo }: { onClose: () => void; returnTo: React.RefObject<HTMLElement | null> }) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const dur = reduced ? 0 : D_FAST + 0.03;

  // Scroll lock without a layout jump (the scrollbar's width is replaced by padding), page inert underneath.
  useEffect(() => {
    const html = document.documentElement;
    const root = document.getElementById("root");
    const prev = { overflow: html.style.overflow, pad: html.style.paddingRight };
    const sb = window.innerWidth - html.clientWidth;
    html.style.overflow = "hidden";
    if (sb > 0) html.style.paddingRight = `${sb}px`;
    root?.setAttribute("inert", "");
    return () => {
      html.style.overflow = prev.overflow;
      html.style.paddingRight = prev.pad;
      root?.removeAttribute("inert");
      returnTo.current?.focus();
    };
  }, [returnTo]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      if (e.key !== "Tab" || !panel.current) return;
      const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(el => el.offsetParent !== null);
      if (items.length === 0) return;
      const first = items[0], last = items[items.length - 1];
      const at = document.activeElement;
      if (!panel.current.contains(at)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && at === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="so-root">
      <m.div
        className="so-backdrop" aria-hidden="true" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        transition={{ duration: dur, ease: EASE_OUT }}
      />
      <m.div
        ref={panel}
        className="so-panel" role="dialog" aria-modal="true" aria-label="Search teams, players and events"
        initial={reduced ? false : { opacity: 0, y: -16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={reduced ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, y: -10, scale: 0.98, transition: { duration: D_FAST, ease: EASE_OUT } }}
        transition={{ duration: dur, ease: EASE_OUT }}
      >
        <div className="so-panel-in">
          <SearchPanel
            variant="overlay" query={query} onQueryChange={setQuery} autoFocus replaceOnOpen inputRef={input}
            headExtra={<button type="button" className="so-close" onClick={onClose} aria-label="Close search"><span aria-hidden="true">Esc</span><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19" /></svg></button>}
          />
        </div>
      </m.div>
    </div>
  );
}

export default function SearchOverlay({ open, onClose, returnTo }: { open: boolean; onClose: () => void; returnTo: React.RefObject<HTMLElement | null> }) {
  return createPortal(
    <AnimatePresence>{open && <Dialog key="search-overlay" onClose={onClose} returnTo={returnTo} />}</AnimatePresence>,
    document.body,
  );
}
