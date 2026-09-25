import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./styles.css";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Matches from "./pages/Matches";
import MatchCenter from "./pages/MatchCenter";
import Rankings from "./pages/Rankings";
import Edge from "./pages/Edge";
import TrackRecord from "./pages/TrackRecord";
import About from "./pages/About";
import NotFound from "./pages/NotFound";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="matches" element={<Matches />} />
          <Route path="match/:id" element={<MatchCenter />} />
          <Route path="rankings" element={<Rankings />} />
          <Route path="edge" element={<Edge />} />
          <Route path="track-record" element={<TrackRecord />} />
          <Route path="about" element={<About />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
