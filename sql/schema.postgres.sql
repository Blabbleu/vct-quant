-- PostgreSQL 15+ DDL for harvesting the vlrggapi v2 API.
-- Documentation: https://github.com/axsddlr/vlrggapi#v2-endpoints
--
-- The raw layer makes ingestion replayable when the unofficial API changes.
-- Core entities are current-state upserts; ratings, rosters, rankings, and
-- aggregate statistics are time-series snapshots.

BEGIN;
CREATE SCHEMA IF NOT EXISTS vlr;
SET search_path TO vlr, public;

-- Harvest lineage -----------------------------------------------------------

CREATE TABLE harvest_run (
    harvest_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_name text NOT NULL,
    api_base_url text NOT NULL,
    api_version text NOT NULL DEFAULT 'v2',
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),
    request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    error_count integer NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    error_message text,
    metadata jsonb NOT NULL DEFAULT '{}',
    CHECK (completed_at IS NULL OR completed_at >= started_at),
    CHECK (status = 'running' OR completed_at IS NOT NULL)
);

CREATE TABLE api_response (
    api_response_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    harvest_run_id bigint NOT NULL REFERENCES harvest_run ON DELETE CASCADE,
    endpoint text NOT NULL,
    query_params jsonb NOT NULL DEFAULT '{}',
    requested_at timestamptz NOT NULL DEFAULT now(),
    responded_at timestamptz,
    http_status integer CHECK (http_status BETWEEN 100 AND 599),
    api_status text,
    response_body jsonb,
    response_sha256 text CHECK (
        response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$'
    ),
    error_message text,
    CHECK (responded_at IS NULL OR responded_at >= requested_at)
);

CREATE INDEX ix_api_response_run ON api_response (harvest_run_id, requested_at);
CREATE INDEX ix_api_response_endpoint ON api_response (endpoint, requested_at DESC);
CREATE INDEX ix_api_response_body_gin ON api_response USING gin (response_body);

-- Stable entities -----------------------------------------------------------

CREATE TABLE team (
    team_id bigint PRIMARY KEY CHECK (team_id > 0),
    name text NOT NULL,
    tag text,
    country text,
    logo_url text,
    total_winnings_raw text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX ix_team_name_lower ON team (lower(name));

CREATE TABLE player (
    player_id bigint PRIMARY KEY CHECK (player_id > 0),
    handle text NOT NULL,
    real_name text,
    country text,
    avatar_url text,
    total_winnings_raw text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX ix_player_handle_lower ON player (lower(handle));

CREATE TABLE event (
    event_id bigint PRIMARY KEY CHECK (event_id > 0),
    name text NOT NULL,
    series_name text,
    status text,
    region_code text,
    start_date date,
    end_date date,
    dates_raw text,
    prize_pool_raw text,
    location text,
    logo_url text,
    vlr_url text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);
CREATE INDEX ix_event_name_lower ON event (lower(name));
CREATE INDEX ix_event_dates ON event (start_date, end_date);

CREATE TABLE player_social (
    player_id bigint NOT NULL REFERENCES player ON DELETE CASCADE,
    platform text NOT NULL,
    url text NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, platform, url)
);

CREATE TABLE team_social (
    team_id bigint NOT NULL REFERENCES team ON DELETE CASCADE,
    platform text NOT NULL,
    url text NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, platform, url)
);

-- Matches -------------------------------------------------------------------

CREATE TABLE match (
    match_id bigint PRIMARY KEY CHECK (match_id > 0),
    event_id bigint REFERENCES event ON DELETE SET NULL,
    event_name text,
    event_series text,
    status text,
    scheduled_at timestamptz,
    completed_at timestamptz,
    date_raw text,
    best_of smallint CHECK (best_of IS NULL OR best_of > 0),
    map_vetos text,
    vlr_url text,
    tournament_icon_url text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    CHECK (last_seen_at >= first_seen_at),
    CHECK (completed_at IS NULL OR scheduled_at IS NULL OR completed_at >= scheduled_at)
);
CREATE INDEX ix_match_event ON match (event_id, scheduled_at);
CREATE INDEX ix_match_status_time ON match (status, scheduled_at);

CREATE TABLE match_team (
    match_id bigint NOT NULL REFERENCES match ON DELETE CASCADE,
    team_number smallint NOT NULL CHECK (team_number IN (1, 2)),
    team_id bigint REFERENCES team ON DELETE SET NULL,
    team_name text NOT NULL,
    flag_code text,
    logo_url text,
    series_score smallint CHECK (series_score IS NULL OR series_score >= 0),
    is_winner boolean,
    PRIMARY KEY (match_id, team_number),
    UNIQUE (match_id, team_id)
);
CREATE INDEX ix_match_team_team ON match_team (team_id, match_id);

CREATE TABLE match_map (
    match_map_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id bigint NOT NULL REFERENCES match ON DELETE CASCADE,
    map_number smallint NOT NULL CHECK (map_number > 0),
    map_name text NOT NULL,
    picked_by_team_id bigint REFERENCES team ON DELETE SET NULL,
    picked_by_raw text,
    duration_seconds integer CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    status text,
    UNIQUE (match_id, map_number)
);

CREATE TABLE match_map_team_score (
    match_map_id bigint NOT NULL REFERENCES match_map ON DELETE CASCADE,
    team_number smallint NOT NULL CHECK (team_number IN (1, 2)),
    team_id bigint REFERENCES team ON DELETE SET NULL,
    total_rounds smallint CHECK (total_rounds IS NULL OR total_rounds >= 0),
    attack_rounds smallint CHECK (attack_rounds IS NULL OR attack_rounds >= 0),
    defense_rounds smallint CHECK (defense_rounds IS NULL OR defense_rounds >= 0),
    overtime_rounds smallint CHECK (overtime_rounds IS NULL OR overtime_rounds >= 0),
    PRIMARY KEY (match_map_id, team_number)
);

CREATE TABLE match_map_player_stat (
    match_map_id bigint NOT NULL REFERENCES match_map ON DELETE CASCADE,
    team_number smallint NOT NULL CHECK (team_number IN (1, 2)),
    player_slot smallint NOT NULL CHECK (player_slot > 0),
    player_id bigint REFERENCES player ON DELETE SET NULL,
    player_handle text NOT NULL,
    agent_name text,
    rating numeric(6,3),
    acs numeric(7,2),
    kills smallint CHECK (kills IS NULL OR kills >= 0),
    deaths smallint CHECK (deaths IS NULL OR deaths >= 0),
    assists smallint CHECK (assists IS NULL OR assists >= 0),
    kill_death_diff smallint,
    kast_pct numeric(5,2) CHECK (kast_pct IS NULL OR kast_pct BETWEEN 0 AND 100),
    adr numeric(7,2),
    headshot_pct numeric(5,2) CHECK (headshot_pct IS NULL OR headshot_pct BETWEEN 0 AND 100),
    first_kills smallint CHECK (first_kills IS NULL OR first_kills >= 0),
    first_deaths smallint CHECK (first_deaths IS NULL OR first_deaths >= 0),
    first_kill_diff smallint,
    PRIMARY KEY (match_map_id, team_number, player_slot),
    UNIQUE (match_map_id, player_id)
);
CREATE INDEX ix_map_player_stat_player ON match_map_player_stat (player_id, match_map_id);
CREATE INDEX ix_map_player_stat_rating ON match_map_player_stat (rating DESC NULLS LAST);

CREATE TABLE match_round (
    match_map_id bigint NOT NULL REFERENCES match_map ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number > 0),
    winner_team_number smallint CHECK (winner_team_number IN (1, 2)),
    winner_team_id bigint REFERENCES team ON DELETE SET NULL,
    winner_side text CHECK (
        winner_side IS NULL OR lower(winner_side) IN ('attack', 'defense', 't', 'ct')
    ),
    win_condition text,
    round_details jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (match_map_id, round_number)
);

CREATE TABLE match_player_kill_matrix (
    match_id bigint NOT NULL REFERENCES match ON DELETE CASCADE,
    player_id bigint REFERENCES player ON DELETE SET NULL,
    player_handle text NOT NULL,
    opponent_player_id bigint REFERENCES player ON DELETE SET NULL,
    opponent_handle text NOT NULL,
    kills smallint NOT NULL CHECK (kills >= 0),
    PRIMARY KEY (match_id, player_handle, opponent_handle)
);

CREATE TABLE match_player_advanced_stat (
    match_id bigint NOT NULL REFERENCES match ON DELETE CASCADE,
    player_id bigint REFERENCES player ON DELETE SET NULL,
    player_handle text NOT NULL,
    two_kills smallint, three_kills smallint, four_kills smallint, five_kills smallint,
    one_vs_one smallint, one_vs_two smallint, one_vs_three smallint,
    one_vs_four smallint, one_vs_five smallint,
    raw_stats jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (match_id, player_handle),
    CHECK (
        coalesce(two_kills, 0) >= 0 AND coalesce(three_kills, 0) >= 0
        AND coalesce(four_kills, 0) >= 0 AND coalesce(five_kills, 0) >= 0
        AND coalesce(one_vs_one, 0) >= 0 AND coalesce(one_vs_two, 0) >= 0
        AND coalesce(one_vs_three, 0) >= 0 AND coalesce(one_vs_four, 0) >= 0
        AND coalesce(one_vs_five, 0) >= 0
    )
);

CREATE TABLE match_team_economy (
    match_id bigint NOT NULL REFERENCES match ON DELETE CASCADE,
    team_id bigint REFERENCES team ON DELETE SET NULL,
    team_name text NOT NULL,
    pistol_win_pct numeric(5,2),
    eco_win_pct numeric(5,2),
    semi_eco_win_pct numeric(5,2),
    semi_buy_win_pct numeric(5,2),
    full_buy_win_pct numeric(5,2),
    raw_stats jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (match_id, team_name),
    CHECK (
        coalesce(pistol_win_pct, 0) BETWEEN 0 AND 100
        AND coalesce(eco_win_pct, 0) BETWEEN 0 AND 100
        AND coalesce(semi_eco_win_pct, 0) BETWEEN 0 AND 100
        AND coalesce(semi_buy_win_pct, 0) BETWEEN 0 AND 100
        AND coalesce(full_buy_win_pct, 0) BETWEEN 0 AND 100
    )
);

CREATE TABLE match_head_to_head (
    match_id bigint NOT NULL REFERENCES match ON DELETE CASCADE,
    occurrence_number smallint NOT NULL CHECK (occurrence_number > 0),
    prior_match_id bigint REFERENCES match ON DELETE SET NULL,
    event_name text,
    match_date date,
    date_raw text,
    score_raw text,
    vlr_url text,
    PRIMARY KEY (match_id, occurrence_number),
    CHECK (prior_match_id IS NULL OR prior_match_id <> match_id)
);

CREATE TABLE match_vod (
    match_id bigint NOT NULL REFERENCES match ON DELETE CASCADE,
    vod_number smallint NOT NULL CHECK (vod_number > 0),
    name text,
    url text NOT NULL,
    PRIMARY KEY (match_id, vod_number),
    UNIQUE (match_id, url)
);

-- Events --------------------------------------------------------------------

CREATE TABLE event_team (
    event_id bigint NOT NULL REFERENCES event ON DELETE CASCADE,
    team_id bigint NOT NULL REFERENCES team ON DELETE CASCADE,
    qualification text,
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, team_id)
);

CREATE TABLE event_team_player (
    event_id bigint NOT NULL,
    team_id bigint NOT NULL,
    player_id bigint NOT NULL REFERENCES player ON DELETE CASCADE,
    player_name text NOT NULL,
    flag_code text,
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, team_id, player_id),
    FOREIGN KEY (event_id, team_id) REFERENCES event_team ON DELETE CASCADE
);

CREATE TABLE event_prize (
    event_prize_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES event ON DELETE CASCADE,
    placement text NOT NULL,
    team_id bigint REFERENCES team ON DELETE SET NULL,
    team_name text,
    amount numeric(14,2) CHECK (amount IS NULL OR amount >= 0),
    currency_code char(3),
    amount_raw text,
    UNIQUE NULLS NOT DISTINCT (event_id, placement, team_id, team_name)
);

-- Standings columns differ by event/stage (for example W/L/RD/MRD), so each
-- source row is retained as JSONB while common team fields remain queryable.
CREATE TABLE event_standing_row (
    event_id bigint NOT NULL REFERENCES event ON DELETE CASCADE,
    stage_name text NOT NULL,
    row_number smallint NOT NULL CHECK (row_number > 0),
    team_id bigint REFERENCES team ON DELETE SET NULL,
    team_name text,
    columns jsonb NOT NULL DEFAULT '[]',
    row_data jsonb NOT NULL,
    PRIMARY KEY (event_id, stage_name, row_number),
    CHECK (jsonb_typeof(columns) = 'array'),
    CHECK (jsonb_typeof(row_data) = 'object')
);

-- Profiles, roster history, and transactions --------------------------------

CREATE TABLE team_roster_snapshot (
    team_id bigint NOT NULL REFERENCES team ON DELETE CASCADE,
    observed_at timestamptz NOT NULL,
    roster_slot smallint NOT NULL CHECK (roster_slot > 0),
    player_id bigint REFERENCES player ON DELETE SET NULL,
    alias text NOT NULL,
    real_name text,
    role text,
    is_captain boolean,
    avatar_url text,
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    PRIMARY KEY (team_id, observed_at, roster_slot)
);
CREATE INDEX ix_team_roster_player ON team_roster_snapshot (player_id, observed_at DESC);

CREATE TABLE player_team_history (
    player_id bigint NOT NULL REFERENCES player ON DELETE CASCADE,
    team_name text NOT NULL,
    team_id bigint REFERENCES team ON DELETE SET NULL,
    relationship_status text NOT NULL,
    date_range_raw text,
    observed_at timestamptz NOT NULL,
    PRIMARY KEY (player_id, team_name, relationship_status, observed_at)
);

CREATE TABLE player_event_placement (
    player_id bigint NOT NULL REFERENCES player ON DELETE CASCADE,
    event_name text NOT NULL,
    event_id bigint REFERENCES event ON DELETE SET NULL,
    placement text NOT NULL,
    team_name text,
    team_id bigint REFERENCES team ON DELETE SET NULL,
    prize_raw text,
    observed_at timestamptz NOT NULL,
    PRIMARY KEY (player_id, event_name, placement, observed_at)
);

CREATE TABLE team_event_placement (
    team_id bigint NOT NULL REFERENCES team ON DELETE CASCADE,
    event_name text NOT NULL,
    event_id bigint REFERENCES event ON DELETE SET NULL,
    placement text NOT NULL,
    prize_raw text,
    observed_at timestamptz NOT NULL,
    PRIMARY KEY (team_id, event_name, placement, observed_at)
);

CREATE TABLE team_transaction (
    team_transaction_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id bigint NOT NULL REFERENCES team ON DELETE CASCADE,
    transaction_date date,
    date_raw text NOT NULL,
    action text NOT NULL,
    player_id bigint REFERENCES player ON DELETE SET NULL,
    player_name text NOT NULL,
    position text,
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    UNIQUE NULLS NOT DISTINCT (
        team_id, transaction_date, date_raw, action, player_name, position
    )
);
CREATE INDEX ix_team_transaction_date ON team_transaction (team_id, transaction_date DESC);

-- Time-varying snapshots -----------------------------------------------------

CREATE TABLE team_rating_snapshot (
    team_id bigint NOT NULL REFERENCES team ON DELETE CASCADE,
    observed_at timestamptz NOT NULL,
    vlr_rating numeric(10,2),
    rank integer CHECK (rank IS NULL OR rank > 0),
    region_code text,
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    PRIMARY KEY (team_id, observed_at)
);

CREATE TABLE team_map_stat_snapshot (
    team_id bigint NOT NULL REFERENCES team ON DELETE CASCADE,
    observed_at timestamptz NOT NULL,
    map_name text NOT NULL,
    games integer, wins integer, losses integer,
    win_pct numeric(5,2),
    attack_first integer, defense_first integer,
    attack_round_wins integer, attack_round_losses integer,
    attack_round_win_pct numeric(5,2),
    defense_round_wins integer, defense_round_losses integer,
    defense_round_win_pct numeric(5,2),
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    PRIMARY KEY (team_id, observed_at, map_name),
    CHECK (
        coalesce(games, 0) >= 0 AND coalesce(wins, 0) >= 0
        AND coalesce(losses, 0) >= 0 AND coalesce(attack_first, 0) >= 0
        AND coalesce(defense_first, 0) >= 0
        AND coalesce(attack_round_wins, 0) >= 0
        AND coalesce(attack_round_losses, 0) >= 0
        AND coalesce(defense_round_wins, 0) >= 0
        AND coalesce(defense_round_losses, 0) >= 0
        AND coalesce(win_pct, 0) BETWEEN 0 AND 100
        AND coalesce(attack_round_win_pct, 0) BETWEEN 0 AND 100
        AND coalesce(defense_round_win_pct, 0) BETWEEN 0 AND 100
    )
);

CREATE TABLE player_agent_stat_snapshot (
    player_id bigint NOT NULL REFERENCES player ON DELETE CASCADE,
    observed_at timestamptz NOT NULL,
    timespan text NOT NULL CHECK (timespan IN ('30d', '60d', '90d', 'all')),
    agent_name text NOT NULL,
    use_count integer, use_pct numeric(5,2), rounds integer,
    rating numeric(6,3), acs numeric(7,2), kd_ratio numeric(7,3),
    adr numeric(7,2), kast_pct numeric(5,2),
    kills_per_round numeric(6,3), assists_per_round numeric(6,3),
    first_kills_per_round numeric(6,3), first_deaths_per_round numeric(6,3),
    kills integer, deaths integer, assists integer, first_kills integer, first_deaths integer,
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    PRIMARY KEY (player_id, observed_at, timespan, agent_name),
    CHECK (
        coalesce(use_count, 0) >= 0 AND coalesce(rounds, 0) >= 0
        AND coalesce(kills, 0) >= 0 AND coalesce(deaths, 0) >= 0
        AND coalesce(assists, 0) >= 0 AND coalesce(first_kills, 0) >= 0
        AND coalesce(first_deaths, 0) >= 0
        AND coalesce(use_pct, 0) BETWEEN 0 AND 100
        AND coalesce(kast_pct, 0) BETWEEN 0 AND 100
    )
);

-- /v2/stats does not expose a stable player ID, so handle is part of the key.
CREATE TABLE player_leaderboard_snapshot (
    harvest_run_id bigint NOT NULL REFERENCES harvest_run ON DELETE CASCADE,
    region text NOT NULL,
    timespan text NOT NULL CHECK (timespan IN ('30', '60', '90', 'all')),
    player_handle text NOT NULL,
    player_id bigint REFERENCES player ON DELETE SET NULL,
    organization text,
    rating numeric(6,3),
    average_combat_score numeric(7,2),
    kill_death_ratio numeric(7,3),
    kast_pct numeric(5,2),
    average_damage_per_round numeric(7,2),
    kills_per_round numeric(6,3),
    assists_per_round numeric(6,3),
    first_kills_per_round numeric(6,3),
    first_deaths_per_round numeric(6,3),
    headshot_pct numeric(5,2),
    clutch_success_pct numeric(5,2),
    clutch_wins integer,
    clutch_attempts integer,
    PRIMARY KEY (harvest_run_id, region, timespan, player_handle),
    CHECK (
        coalesce(kast_pct, 0) BETWEEN 0 AND 100
        AND coalesce(headshot_pct, 0) BETWEEN 0 AND 100
        AND coalesce(clutch_success_pct, 0) BETWEEN 0 AND 100
        AND coalesce(clutch_wins, 0) >= 0
        AND coalesce(clutch_attempts, 0) >= 0
    )
);
CREATE INDEX ix_player_leaderboard_player
    ON player_leaderboard_snapshot (player_id, harvest_run_id);

CREATE TABLE team_ranking_snapshot (
    harvest_run_id bigint NOT NULL REFERENCES harvest_run ON DELETE CASCADE,
    region_code text NOT NULL,
    rank integer NOT NULL CHECK (rank > 0),
    team_name text NOT NULL,
    team_id bigint REFERENCES team ON DELETE SET NULL,
    country text,
    last_played_raw text,
    last_opponent_raw text,
    record_raw text,
    earnings_raw text,
    logo_url text,
    PRIMARY KEY (harvest_run_id, region_code, rank),
    UNIQUE (harvest_run_id, region_code, team_name)
);
CREATE INDEX ix_team_ranking_team ON team_ranking_snapshot (team_id, harvest_run_id);

-- News ----------------------------------------------------------------------

CREATE TABLE news_article (
    article_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    description text,
    published_date date,
    date_raw text,
    author text,
    vlr_url text NOT NULL UNIQUE,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    source_response_id bigint REFERENCES api_response ON DELETE SET NULL,
    CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX ix_news_published ON news_article (published_date DESC);

COMMIT;
