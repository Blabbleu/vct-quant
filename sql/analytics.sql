-- Example analytical queries against the DuckDB schema.

-- Team map winrates (from harvested map scores).
WITH map_result AS (
    SELECT
        a.match_map_id,
        mm.map_name,
        a.team_id,
        a.total_rounds AS rounds_for,
        b.total_rounds AS rounds_against
    FROM match_map_team_score a
    JOIN match_map_team_score b
        ON b.match_map_id = a.match_map_id AND b.team_number <> a.team_number
    JOIN match_map mm ON mm.match_map_id = a.match_map_id
    WHERE a.team_id IS NOT NULL
)
SELECT
    t.name AS team,
    map_name,
    count(*) AS maps_played,
    sum(CASE WHEN rounds_for > rounds_against THEN 1 ELSE 0 END) AS wins,
    round(100.0 * wins / maps_played, 1) AS win_pct
FROM map_result
JOIN team t ON t.team_id = map_result.team_id
GROUP BY t.name, map_name
HAVING count(*) >= 5
ORDER BY team, win_pct DESC;

-- Player form: average rating over their last 10 maps.
SELECT
    p.handle,
    avg(s.rating) AS avg_rating,
    count(*) AS maps
FROM (
    SELECT
        player_id,
        rating,
        row_number() OVER (PARTITION BY player_id ORDER BY match_map_id DESC) AS rn
    FROM match_map_player_stat
    WHERE player_id IS NOT NULL AND rating IS NOT NULL
) s
JOIN player p ON p.player_id = s.player_id
WHERE s.rn <= 10
GROUP BY p.handle
HAVING count(*) >= 5
ORDER BY avg_rating DESC;
