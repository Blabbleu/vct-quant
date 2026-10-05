import { useEffect, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import SearchPanel from "../components/SearchPanel";
import { PageFade } from "../lib/motion";
import { SEARCH_DEBOUNCE_MS } from "../lib/searchModel";
import "./Search.css";

/** /search?q= : the same search panel rendered full-page (deep links stay shareable). */
export default function Search() {
  const [params, setParams] = useSearchParams();
  const [input, setInput] = useState(() => params.get("q") ?? "");
  const inputRef = useRef<HTMLInputElement>(null);
  const location = useLocation();
  const focusRequested = (location.state as { focus?: boolean } | null)?.focus === true;

  useEffect(() => {
    if (focusRequested) inputRef.current?.focus();
  }, [focusRequested, location.key]);

  // URL -> input (back/forward, deep links).
  useEffect(() => {
    const query = params.get("q") ?? "";
    setInput(current => current === query ? current : query);
  }, [params]);

  // input -> URL, debounced like the lookup.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams();
      if (input.trim()) next.set("q", input);
      setParams(next, { replace: true });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [input, setParams]);

  return (
    <PageFade className="search-page">
      <header className="page-head">
        <h1>Search</h1>
        <p className="lede">Find Tier 1 and Tier 2 teams, players, and events by name, tag, or vlr.gg ID.</p>
      </header>
      <SearchPanel variant="page" query={input} onQueryChange={setInput} inputRef={inputRef} />
    </PageFade>
  );
}
