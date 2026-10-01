import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { getTheme, toggleTheme, type Theme } from "../lib/theme";

/** Visible on phone: the rest live in the overflow menu. */
const PRIMARY = [
  { to: "/matches", label: "Matches" },
  { to: "/results", label: "Results" },
];
const MORE = [
  { to: "/rankings", label: "Ranks" },
  { to: "/champions/2766", label: "Champions" },
  { to: "/edge", label: "Edge" },
  { to: "/track-record", label: "Record" },
  { to: "/about", label: "About" },
  { to: "/status", label: "Status" },
];

function NavTab({ to, label, className = "" }: { to: string; label: string; className?: string }) {
  return (
    <NavLink to={to} className={({ isActive }) => `nav-tab${isActive ? " nav-tab-active" : ""}${className ? ` ${className}` : ""}`}>
      <span>{label}</span>
    </NavLink>
  );
}

export default function Layout() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [theme, setThemeState] = useState<Theme>(() => getTheme());
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

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

  // "/" jumps to search from anywhere (not while typing in a field).
  useEffect(() => {
    function onSlash(e: KeyboardEvent) {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      e.preventDefault();
      const field = document.getElementById("entity-search");
      if (field) field.focus();
      else navigate("/search", { state: { focus: true } });
    }
    document.addEventListener("keydown", onSlash);
    return () => document.removeEventListener("keydown", onSlash);
  }, [navigate]);

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
            {PRIMARY.map(n => <NavTab key={n.to} to={n.to} label={n.label} className={n.to === "/results" ? "nav-wide-only" : ""} />)}
            {/* Merges into the same flex row at >=1200px; hidden below that. */}
            <div className="nav-more">
              {MORE.map(n => <NavTab key={n.to} to={n.to} label={n.label} />)}
              <button type="button" className="nav-tab" onClick={toggleTheme}>
                <span>{themeLabel}</span>
              </button>
            </div>
          </nav>
          <Link to="/search" className={`nav-search${pathname === "/search" ? " nav-search-active" : ""}`}
            aria-label="Search (press /)" title="Search (/)">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square" aria-hidden="true">
              <circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5 21 21" />
            </svg>
          </Link>
          <div className="nav-overflow" ref={menuRef}>
            <button type="button" className="nav-overflow-btn" aria-haspopup="menu" aria-expanded={open}
              aria-label="More navigation" onClick={() => setOpen(o => !o)}>
              <span aria-hidden="true">&#8942;</span>
            </button>
            {open && (
              <div className="nav-overflow-panel" role="menu">
                <NavTab to="/results" label="Results" className="nav-narrow-only" />
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
