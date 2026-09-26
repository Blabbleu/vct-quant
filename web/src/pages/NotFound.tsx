import { Link, useLocation } from "react-router-dom";
import Panel from "../components/arena/Panel";
import "./NotFound.css";

const EXITS = [
  { to: "/matches", label: "Matches", line: "Upcoming forecasts" },
  { to: "/results", label: "Results", line: "Finished matches" },
  { to: "/rankings", label: "Ranks", line: "Elo table" },
  { to: "/champions/2766", label: "Champions", line: "Group stage" },
];

/** Unknown route: the empty-state look plus the main exits, so it's never a dead end. */
export default function NotFound() {
  const { pathname } = useLocation();
  return (
    <div className="notfound-page">
      <Panel cut="l" frame="line">
        <div className="notfound-in">
          <h1 className="notfound-title">Page not found</h1>
          <p className="notfound-path num">{pathname}</p>
          <p className="notfound-line">That page doesn't exist. It may have moved, or the link is wrong.</p>
          <Link to="/" className="btn btn-primary slant notfound-home"><span>Back to home</span></Link>
        </div>
      </Panel>
      <nav className="notfound-exits" aria-label="Main pages">
        {EXITS.map(e => (
          <Link key={e.to} to={e.to} className="notfound-exit cut-m">
            <span className="notfound-exit-label">{e.label}</span>
            <span className="notfound-exit-line">{e.line}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}
