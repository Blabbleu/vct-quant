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
export interface ShadowScore { n: number; elo: number; shadow: number }
export interface Live {
  logged: number; graded: number; rows: GradedRow[];
  log_loss: number | null; brier: number | null;
  market: { n: number; elo: number; market: number } | null;
  shadows: Record<string, ShadowScore>;
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
export interface MovementPoint { observed_at: string; elo: number; market: number | null; spread: number | null }
export interface FormResult { match_id: number; opponent: string; result: "W" | "L"; completed_at: string }
export interface MapRecord { map: string; played: number; won: number; round_share: number }
export interface Movement {
  match_id: number; team_a: string; team_b: string; scheduled_at: string;
  team_a_key: string; team_b_key: string;
  logo_a?: string | null; logo_b?: string | null; tag_a?: string | null; tag_b?: string | null;
  recent_form: { a: FormResult[]; b: FormResult[] };
  map_pool: { a: MapRecord[]; b: MapRecord[] };
  points: MovementPoint[]; note: string;
}
