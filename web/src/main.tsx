import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "@fontsource-variable/inter/wght.css";
import "./styles.css";
import "./lib/theme";
import { installPrefetch, loadChampions, loadedChampions } from "./lib/prefetch";
import Layout from "./components/Layout";
import { MotionProvider } from "./lib/motion";
import { LoadingBlocks } from "./components/arena/States";
import Home from "./pages/Home";
import Matches from "./pages/Matches";
import Results from "./pages/Results";
import MatchCenter from "./pages/MatchCenter";
import Team from "./pages/Team";
import Player from "./pages/Player";
import Rankings from "./pages/Rankings";
import Edge from "./pages/Edge";
import TrackRecord from "./pages/TrackRecord";
import About from "./pages/About";
import Status from "./pages/Status";
const LazyChampions = lazy(loadChampions);
/** Straight to the page when the chunk was prefetched; Suspense only on a cold deep link. */
function ChampionsRoute() {
  const Loaded = loadedChampions();
  return Loaded ? <Loaded /> : <Suspense fallback={<LoadingBlocks label="Loading Champions&hellip;" />}><LazyChampions /></Suspense>;
}
import NotFound from "./pages/NotFound";
import ArenaKit from "./pages/ArenaKit";
import Search from "./pages/Search";

installPrefetch();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MotionProvider>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="matches" element={<Matches />} />
          <Route path="results" element={<Results />} />
          <Route path="match/:id" element={<MatchCenter />} />
          <Route path="team/:id" element={<Team />} />
          <Route path="player/:id" element={<Player />} />
          <Route path="champions/2766" element={<ChampionsRoute />} />
          <Route path="rankings" element={<Rankings />} />
          <Route path="edge" element={<Edge />} />
          <Route path="track-record" element={<TrackRecord />} />
          <Route path="about" element={<About />} />
          <Route path="status" element={<Status />} />
          <Route path="search" element={<Search />} />
          <Route path="arena" element={<ArenaKit />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
    </MotionProvider>
  </StrictMode>,
);
