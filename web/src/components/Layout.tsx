import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";

const NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/matches", label: "Matches" },
  { to: "/rankings", label: "Rankings" },
  { to: "/edge", label: "Edge" },
  { to: "/track-record", label: "Track record" },
  { to: "/about", label: "How it works" },
];

export default function Layout() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <NavLink to="/" className="brand">VCT<span>Quant</span></NavLink>
          <nav className="nav" aria-label="Main">
            {NAV.map(n => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive }) => (isActive ? "active" : undefined)}>{n.label}</NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="wrap"><Outlet /></main>
      <footer className="foot">
        Forecasts are model estimates, not betting advice. Data: vlr.gg, Polymarket.
      </footer>
    </>
  );
}
