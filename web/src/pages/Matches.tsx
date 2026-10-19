import { useState } from "react";
import { useChampionsStatus, useResults, useSnapshot } from "../lib/api";
import { LoadingBlocks, ErrorPanel } from "../components/arena/States";
import MatchesView from "../components/matches/MatchesView";

export default function Matches() {
  const snapshot = useSnapshot();
  const results = useResults();
  const champions = useChampionsStatus();
  const [event, setEvent] = useState("all");

  if (snapshot.loading) return <LoadingBlocks label="Loading matches\u2026" />;
  if (snapshot.error || !snapshot.data) return <ErrorPanel detail={snapshot.error ?? "no data"} onRetry={() => location.reload()} />;

  return <MatchesView data={snapshot.data} results={results} champions={champions} event={event} setEvent={setEvent} />;
}
