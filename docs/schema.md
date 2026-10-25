# Wickets.ai database (DuckDB SQL dialect)

One row per delivery for every T20 International in the database. Read-only.

## Tables

### deliveries: one row per ball (1.34M rows)
| column | meaning |
|---|---|
| match_id, innings | innings 1-2; 3+ are super overs (`is_super_over`) |
| over | **0-indexed**: over 0 is the 1st over, over 19 the 20th |
| ball | sequence within the over, counting wides/no-balls (1-based) |
| batting_team, bowling_team | team names, e.g. 'India', 'United Arab Emirates' |
| batter_id, non_striker_id, bowler_id | `players.player_id` |
| runs_batter | runs off the bat |
| extras, wides, noballs, byes, legbyes, penalty | extras on the ball |
| total_runs | runs_batter + all extras |
| wicket_kind, player_out_id | first dismissal on the ball (use `wickets` for all; two on one ball is rare) |
| is_legal_ball | not a wide and not a no-ball |
| is_ball_faced | counts as a ball faced by the batter (everything except wides) |
| runs_conceded | charged to the bowler: total_runs - byes - legbyes - penalty |
| is_bowler_wkt | a bowler-credited dismissal fell on this ball |
| is_four, is_six | boundary off the bat (all-run 4s excluded) |
| is_dot | legal ball, nothing off the bat, nothing conceded |
| phase | 'powerplay' (over 0-5), 'middle' (6-14), 'death' (15-19) |
| in_powerplay | inside the actual mandatory powerplay recorded for the match |
| is_super_over | super-over ball: exclude from records |

### wickets: one row per dismissal
match_id, innings, over, ball, player_out_id, kind, bowler_id, fielder_ids (VARCHAR[]), is_bowler_wkt.
`kind` values: caught, bowled, run out, lbw, stumped, caught and bowled, retired hurt, hit wicket,
retired out, obstructing the field, retired not out, hit the ball twice, timed out.

### matches: one row per match
match_id (ESPNcricinfo id), t20i_number, gender ('male'/'female'), date, season, venue_id, venue_raw,
city, team1, team2, toss_winner, toss_decision ('bat'/'field'), winner, result ('win'/'tie'/'no result'),
win_by_runs, win_by_wickets, decided_by ('D/L', 'super over', 'bowl out', ...), player_of_match
(VARCHAR[] of scorecard names), event_name, event_match_no, overs_per_side, balls_per_over, source.

### innings: one row per innings
match_id, innings, batting_team, bowling_team, is_super_over, target_runs, target_overs,
penalty_runs_pre, penalty_runs_post, miscounted_overs.

### players: one row per player
player_id, name (scorecard name, e.g. 'JJ Bumrah'), unique_name, cricinfo_id, country (team most often
represented), batting_hand ('right'/'left'), bowling_style (raw text), bowling_arm ('right'/'left'),
bowling_kind ('pace'/'spin'), bowling_type ('fast','fast-medium','medium-fast','medium','off-spin',
'leg-spin','orthodox','wrist-spin'), primary_role, height_cm, profile_source.
Profile columns come from Wikipedia and are NULL when unknown (about 2/3 of Associate players).

### match_roles: one row per player per match
match_id, player_id, team, batting_position (arrival order; NULL = did not bat), captain, wicketkeeper
(always NULL: not in the source).

### venues
venue_id, name, city, country (NULL), aliases (VARCHAR[]).

### player_seasons
Empty in the demo (no speed data). Ball speed, line and length, shot type and field positions are not
available at all.

### coverage_notes
Free-text notes on gaps in the data.

## Views
- **player_index**: player_id, name, unique_name, full_name (e.g. 'Jasprit Bumrah'), country, gender,
  matches, first_match, last_match, batting_hand, bowling_style, bowling_type, primary_role.
  Use it to resolve names. A full name may be NULL for Associate players; search name too.
- **batting_innings**: match_id, innings, player_id, team, runs, balls, fours, sixes. Excludes super
  overs; only batters who faced a ball. Dismissals are in `wickets`.
- **bowling_innings**: match_id, innings, player_id, team, legal_balls, runs_conceded, wickets, dots.
  Excludes super overs.
- **deliveries_ctx**: every `deliveries` column plus gender, date, venue_id, batter_hand,
  bowling_arm, bowling_kind, bowling_type. The usual starting point for ball-level questions.

## Gotchas
- Always filter `NOT is_super_over` for batting, bowling and team records.
- Phase filters: use `phase`, never `over BETWEEN 1 AND 6` (overs are 0-indexed).
- A batter's dismissals: `wickets` where `player_out_id` = the player and
  `kind NOT IN ('retired hurt', 'retired not out')`. Run outs of the non-striker count against the
  non-striker.
- Innings batted: `match_roles.batting_position IS NOT NULL` (includes non-strikers run out without facing).
- Bowler wickets: `wickets.is_bowler_wkt` (or `bowling_innings.wickets`), never count all wickets.
- Head-to-head bowler v batter: deliveries where bowler_id = X and batter_id = Y; the batter's
  dismissals by that bowler are wickets with bowler_id = X, player_out_id = Y and is_bowler_wkt.
- Team innings total = SUM(total_runs) over that innings' deliveries.
- `player_of_match` holds scorecard names (players.name), not ids.
- Overs display: balls b -> `(b // 6) || '.' || (b % 6)`.
- Strings are case-sensitive; team names are full ('United Arab Emirates', 'United States of America').
