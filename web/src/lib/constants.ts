/**
 * Thresholds and fixed honesty copy for the Terminal Arena UI.
 * Never hard-code these inline elsewhere: import from here so every page
 * agrees on the same numbers and wording.
 */

/** Fewer than this many rated matches this season -> LOW DATA chip. */
export const LOW_DATA_MATCHES = 10;

/** Model-vs-market gap at or above this many points -> BIG GAP. */
export const BIG_GAP_POINTS = 10;

/** Gap below this many points reads as AGREE. */
export const AGREE_POINTS = 1;

/** Market spread above this -> WIDE SPREAD, excluded from grading. */
export const WIDE_SPREAD = 0.1;

/** Payload older than this many hours -> stale note. */
export const STALE_HOURS = 6;

/** Fixed honesty copy (spec "Copy and do-nots"). Never paraphrase. */
export const COPY = {
  modelBasis: "Model is Elo ratings only: no map veto or roster news.",
  marketBasis: "Last traded price before start.",
  outcomeSplit: "Derived from the series chance, treating maps as independent.",
  /** Fill in the favourite's name/number and the market's number that was right. */
  upset: (favourite: string, favouritePct: string, rightSide: string, rightPct: string) =>
    `Model missed. It had ${favourite} at ${favouritePct}; the market's ${rightPct} was right (${rightSide}).`,
  edgeDisclaimer: "Paper trading. No real money.",
  noMarket: "MKT --.- \u00B7 NO PRICE YET",
  couldntReach: "COULDN'T REACH THE DATA DESK",
  noMatchesScheduled: "NO MATCHES SCHEDULED",
} as const;
