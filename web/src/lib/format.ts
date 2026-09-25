export const pct = (p: number | null | undefined, digits = 1) =>
  p == null || !Number.isFinite(p) ? "–" : `${(p * 100).toFixed(digits)}%`;

export const num = (v: number | null | undefined, digits = 4) =>
  v == null || !Number.isFinite(v) ? "–" : v.toFixed(digits);

export const int = (v: number) => v.toLocaleString("en-US");

const dtf = new Intl.DateTimeFormat(undefined, {
  weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
});
export const when = (iso: string) => dtf.format(new Date(iso));

export function relative(iso: string, now = Date.now()): string {
  const mins = Math.round((new Date(iso).getTime() - now) / 60000);
  const abs = Math.abs(mins);
  const text = abs < 60 ? `${abs}m` : abs < 48 * 60 ? `${Math.round(abs / 60)}h` : `${Math.round(abs / 1440)}d`;
  return mins >= 0 ? `in ${text}` : `${text} ago`;
}

/** The model's own formula: a 400-point Elo edge is 10:1 series odds. */
export const eloWinProbability = (a: number, b: number) => 1 / (1 + Math.pow(10, (b - a) / 400));

/** A market quote worth comparing against: priced, tight and traded. */
export const liquid = (spread: number | null, volume: number | null) =>
  spread != null && spread <= 0.1 && (volume ?? 0) >= 1000;

export const logLoss = (p: number, won: boolean) => -Math.log(Math.min(Math.max(won ? p : 1 - p, 1e-9), 1));
