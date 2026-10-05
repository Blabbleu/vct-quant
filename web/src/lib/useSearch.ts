import { useCallback, useEffect, useState } from "react";
import { EMPTY_RESULTS, SEARCH_DEBOUNCE_MS, isSearchResults, searchUrl, type SearchResults } from "./searchModel";

export interface SearchState {
  results: SearchResults;
  loading: boolean;
  error: string | null;
  /** True when `results` belong to the current (trimmed) input and nothing is in flight. */
  current: boolean;
  retry: () => void;
}

/** Debounced (200 ms), abortable /api/search lookup shared by the page and the overlay. */
export function useSearch(input: string): SearchState {
  const [results, setResults] = useState<SearchResults>(EMPTY_RESULTS);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resultsFor, setResultsFor] = useState("");
  const [tries, setTries] = useState(0);

  useEffect(() => {
    const trimmed = input.trim();
    const controller = new AbortController();
    if (!trimmed) {
      setResults(EMPTY_RESULTS); setResultsFor(""); setError(null); setLoading(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      fetch(searchUrl(trimmed), { signal: controller.signal })
        .then(async response => {
          if (!response.ok) throw new Error(response.status === 503
            ? "Search is temporarily unavailable. Try again shortly."
            : `Search failed (${response.status}).`);
          return response.json() as Promise<unknown>;
        })
        .then(data => {
          if (!isSearchResults(data)) throw new Error("Search returned an unexpected response.");
          setResults(data);
          setResultsFor(trimmed);
        })
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") return;
          setError(reason instanceof Error ? reason.message : "Search failed.");
          setResults(EMPTY_RESULTS);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [input, tries]);

  const retry = useCallback(() => setTries(n => n + 1), []);
  return { results, loading, error, current: !loading && !error && resultsFor === input.trim() && input.trim() !== "", retry };
}
