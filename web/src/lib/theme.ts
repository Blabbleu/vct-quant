/**
 * Dark/light theme switching for the Terminal Arena UI.
 *
 * On load: use the saved choice (localStorage "vctq-theme") if there is one,
 * otherwise follow the OS `prefers-color-scheme` and keep following it until
 * the viewer picks explicitly. The very first paint is handled by an inline
 * script in index.html (see below) so there is no flash; this module keeps
 * things in sync afterwards and exposes the toggle used by the nav.
 */
export type Theme = "dark" | "light";

const KEY = "vctq-theme";

function systemTheme(): Theme {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function stored(): Theme | null {
  const v = localStorage.getItem(KEY);
  return v === "dark" || v === "light" ? v : null;
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export function getTheme(): Theme {
  return (document.documentElement.dataset.theme as Theme | undefined) ?? stored() ?? systemTheme();
}

export function setTheme(theme: Theme) {
  localStorage.setItem(KEY, theme);
  apply(theme);
  window.dispatchEvent(new CustomEvent("vctq-theme-change", { detail: theme }));
}

export function toggleTheme(): Theme {
  const next: Theme = getTheme() === "dark" ? "light" : "dark";
  setTheme(next);
  return next;
}

// Keep following the OS until the viewer has made an explicit choice.
if (typeof window !== "undefined" && window.matchMedia) {
  apply(stored() ?? systemTheme());
  const mq = window.matchMedia("(prefers-color-scheme: light)");
  const onChange = () => {
    if (!stored()) apply(systemTheme());
  };
  mq.addEventListener ? mq.addEventListener("change", onChange) : mq.addListener(onChange);
}
