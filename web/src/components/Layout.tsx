import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { getTheme, toggleTheme, type Theme } from "../lib/theme";

/** Visible on phone: the rest live in the overflow menu. */
const PRIMARY = [
  { to: "/matches", label: "Matches" },
  { to: "/results", label: "Results" },
  { to: "/rankings", label: "Ranks" },
];
const MORE = [
  { to: "/champions/2766", label: "Champions" },
  { to: "/edge", label: "Edge" },
  { to: "/track-record", label: "Record" },
  { to: "/about", label: "About" },
  { to: "/status", label: "Status" },
];

function NavTab({ to, label }: { to: string; label: string }) {
  return (
    <NavLink to={to} className={({ isActive }) => `nav-tab${isActive ? " nav-tab-active" : ""}`}>
      <span>{label}</span>
    </NavLink>
  );
}

export default function Layout() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [theme, setThemeState] = useState<Theme>(() => getTheme());
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  useEffect(() => { setOpen(false); }, [pathname]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(false); }
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    const onChange = (e: Event) => setThemeState((e as CustomEvent<Theme>).detail);
    window.addEventListener("vctq-theme-change", onChange as EventListener);
    return () => window.removeEventListener("vctq-theme-change", onChange as EventListener);
  }, []);

  const themeLabel = theme === "dark" ? "Light theme" : "Dark theme";

  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <NavLink to="/" className="wordmark slant" aria-label="VCT Quant, home">
            <span>VCT QUANT</span>
          </NavLink>
          <nav className="nav" aria-label="Main">
            {PRIMARY.map(n => <NavTab key={n.to} to={n.to} label={n.label} />)}
            {/* Merges into the same flex row at >=1200px; hidden below that. */}
            <div className="nav-more">
              {MORE.map(n => <NavTab key={n.to} to={n.to} label={n.label} />)}
              <button type="button" className="nav-tab" onClick={toggleTheme}>
                <span>{themeLabel}</span>
              </button>
            </div>
          </nav>
          <div className="nav-overflow" ref={menuRef}>
            <button type="button" className="nav-overflow-btn" aria-haspopup="menu" aria-expanded={open}
              aria-label="More navigation" onClick={() => setOpen(o => !o)}>
              <span aria-hidden="true">&#8942;</span>
            </button>
            {open && (
              <div className="nav-overflow-panel" role="menu">
                {MORE.map(n => <NavTab key={n.to} to={n.to} label={n.label} />)}
                <button type="button" className="nav-tab" role="menuitem" onClick={toggleTheme}>
                  <span>{themeLabel}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="wrap"><Outlet /></main>
      <footer className="foot">
        Forecasts are model estimates, not betting advice. Data: vlr.gg, Polymarket.
      </footer>
    </>
  );
}
