// Shapes returned by server.js (GET-only). Source of truth: src/vct_quant/dashboard.py
// and src/vct_quant/match_center.py.

export interface Fixture {
  match_id: number;
  start: string;
  event: string;
  series: string;
  tier: number;
  best_of: number | null;
  team_a: string;
  team_b: string;
  logo_a: string | null;
  logo_b: string | null;
  tag_a: string | null;
  tag_b: string | null;
  elo_a: number;
  elo_b: number;
  p_a: number;
  p_sweep: number | null;
  matches_a: number;
  matches_b: number;
  market: number | null;
  spread: number | null;
  volume: number | null;
  url: string;
}

export interface CalibrationBucket { predicted: number; actual: number; n: number }
export interface Backtest {
  n: number; log_loss: number; brier: number; accuracy: number;
  folds: { fold: number; n: number; log_loss: number }[];
  calibration: CalibrationBucket[];
}
export interface Ranking { rank: number; team: string; elo: number; matches: number; logo: string | null; tag: string | null }
export interface LedgerRow { name: string; holdout: string; score: string; verdict: string }
export interface GradedRow {
  match_id: number; team_a: string; team_b: string; p: number; won: boolean; market: number | null;
  logo_a: string | null; logo_b: string | null; tag_a: string | null; tag_b: string | null;
}
export interface ShadowScore { n: number; elo: number; shadow: number; t?: number | null }
export interface Checkpoint {
  min_n: number; checkpoint_2_n: number; final_match_id: number; n: number; final_graded: boolean;
  checkpoint_1: {
    n: number; diff: number | null; t: number | null;
    state: "awaiting_final" | "final_graded";
    verdict: "too_few" | "no_worse" | "boundary" | "worse";
  };
  checkpoint_2: { n: number; reached: boolean };
}
export interface Live {
  logged: number; graded: number; rows: GradedRow[];
  log_loss: number | null; brier: number | null;
  market: { n: number; elo: number; market: number } | null;
  shadows: Record<string, ShadowScore>;
  checkpoint?: Checkpoint | null;
}
export interface Snapshot {
  generated_at: string;
  coverage: { matches: number; dated: number; latest_result: string; tier_1: number; tier_2: number; tier_3: number };
  backtest: Backtest;
  gc: { n: number; log_loss: number; k: number; matches: number };
  rankings: Ranking[];
  season: number;
  ledger: LedgerRow[];
  live: Live;
  fixtures: Fixture[];
}
export interface PaperEntry {
  match_id: number; team_a: string; team_b: string; side: "A" | "B";
  entry_at: string; model: number; market_mid: number; entry_price: number;
  last_sampled_market: number | null; sampled_clv: number | null;
  status: "open" | "unverified" | "settled"; return_per_unit: number | null;
}
export interface PaperLedger {
  n: number; settled: number; net_units: number; rows: PaperEntry[]; note: string;
}
export interface MovementPoint { observed_at: string; elo: number; market: number | null; spread: number | null }
export interface FormResult { match_id: number; opponent: string; result: "W" | "L"; completed_at: string }
export interface MapRecord { map: string; played: number; won: number; round_share: number }
export interface TeamProfile {
  team_id: number; name: string; logo: string | null; tag: string | null;
  record: { wins: number; losses: number };
  recent_lineup: { maps_sampled: number; latest_map_date: string | null; latest_match_id: number | null;
    players: { player_id: number; handle: string; maps: number }[] };
  results: {
    match_id: number; completed_at: string; opponent: string; opponent_id: number | null;
    result: "W" | "L"; maps_for: number; maps_against: number;
  }[];
  fixtures: {
    match_id: number; scheduled_at: string; opponent: string; opponent_id: number | null; p_win: number;
  }[];
  note: string;
}
export interface PlayerProfile {
  player_id: number; handle: string; country: string | null; recorded_maps: number;
  maps: {
    match_id: number; completed_at: string; map_number: number; map: string;
    team_id: number; team: string; opponent_id: number; opponent: string;
    agent: string | null; result: "W" | "L" | "D";
    rounds_for: number; rounds_against: number;
    rating: number | null; acs: number | null;
    kills: number | null; deaths: number | null; assists: number | null;
  }[];
  agents: { agent: string; maps: number }[];
  teams: { team_id: number; name: string; maps: number }[];
  note: string;
}
export interface ChampionsSlot { match_id: number; stage: string; team_ids?: number[] }
export interface ChampionsGroup {
  entrants: Record<string, string>;
  slots: Record<"opening_1" | "opening_2" | "winners" | "elimination" | "decider", ChampionsSlot>;
  results: Record<string, { team_ids: number[]; scores: number[] }>;
  expected: Record<string, number[]>;
  qualifiers: number[];
  unverified_match_ids: number[];
}
export interface ChampionsStatus {
  event_id: number; as_of: string | null; playoff_routing: "unresolved";
  title_odds: null; groups: Record<"A" | "B" | "C" | "D", ChampionsGroup>;
}
export interface ResultMap { number: number; map: string; rounds_a: number; rounds_b: number }
export interface MatchResult {
  status: "verified" | "unverified"; reason: string | null; winner: "a" | "b" | null;
  maps_a: number | null; maps_b: number | null; maps: ResultMap[]; maps_complete: boolean;
  pre_start_winner_p: number | null; completed_on: string | null;
  source_url: string | null; as_of: string | null;
}
export interface Movement {
  match_id: number; team_a: string; team_b: string; scheduled_at: string;
  team_a_key: string; team_b_key: string;
  logo_a?: string | null; logo_b?: string | null; tag_a?: string | null; tag_b?: string | null;
  recent_form: { a: FormResult[]; b: FormResult[] };
  map_pool: { a: MapRecord[]; b: MapRecord[] };
  result?: MatchResult | null;
  points: MovementPoint[]; note: string;
}
