import { useEffect, useState } from "react";
import type { Movement, Snapshot } from "./types";

type State<T> = { data: T | null; error: string | null; loading: boolean };

async function getJson<T>(url: string): Promise<T | null> {
  const resp = await fetch(url);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`${url} answered ${resp.status}`);
  return resp.json() as Promise<T>;
}

// One snapshot request per page load, shared by every page that asks.
let snapshotPromise: Promise<Snapshot | null> | null = null;
export function refreshSnapshot() { snapshotPromise = null; }

function useFetch<T>(key: string, load: () => Promise<T | null>): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let alive = true;
    setState(s => ({ ...s, loading: true }));
    load().then(
      data => alive && setState({ data, error: null, loading: false }),
      (err: Error) => alive && setState({ data: null, error: err.message, loading: false }),
    );
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

export function useSnapshot(nonce = 0): State<Snapshot> {
  return useFetch(`snapshot:${nonce}`, () => (snapshotPromise ??= getJson<Snapshot>("/api/snapshot")));
}

export function useMovement(id: number): State<Movement> {
  return useFetch(`match:${id}`, () => getJson<Movement>(`/api/match/${id}`));
}
