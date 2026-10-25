"""Story prompts for writers prepping a match: milestones within reach, active streaks, stat of the day.

There's no fixture feed in the demo, so "upcoming" means players and teams active in the last
120 days of data. Every prompt carries the SQL behind it, like any other answer.
"""
import datetime

ACTIVE_DAYS = 120
FULL_MEMBERS = ("Afghanistan", "Australia", "Bangladesh", "England", "India", "Ireland", "New Zealand",
                "Pakistan", "South Africa", "Sri Lanka", "West Indies", "Zimbabwe")


def _rows(db, sql, params=None):
    return db.query(sql, max_rows=200, params=params).as_dicts()


def milestones(db, gender=None, limit=12):
    g = "AND pi.gender = ?" if gender else ""
    ps = [gender] if gender else []
    runs_sql = f"""
        WITH latest AS (SELECT MAX(date) AS d FROM matches),
        active AS (SELECT r.player_id FROM match_roles r JOIN matches m USING (match_id), latest
                   WHERE m.date >= latest.d - INTERVAL {ACTIVE_DAYS} DAY GROUP BY 1),
        t AS (SELECT pi.player_id, COALESCE(pi.full_name, pi.name) AS player, pi.country, pi.gender,
                     SUM(b.runs) AS total
              FROM batting_innings b JOIN player_index pi USING (player_id)
              WHERE pi.player_id IN (SELECT player_id FROM active) {g} GROUP BY ALL)
        SELECT player, country, gender, total, (total // 1000 + 1) * 1000 AS target,
               (total // 1000 + 1) * 1000 - total AS needed, 'runs' AS stat
        FROM t WHERE total >= 1000 AND (total // 1000 + 1) * 1000 - total <= 150
        ORDER BY needed LIMIT {limit}"""
    wkts_sql = f"""
        WITH latest AS (SELECT MAX(date) AS d FROM matches),
        active AS (SELECT r.player_id FROM match_roles r JOIN matches m USING (match_id), latest
                   WHERE m.date >= latest.d - INTERVAL {ACTIVE_DAYS} DAY GROUP BY 1),
        t AS (SELECT pi.player_id, COALESCE(pi.full_name, pi.name) AS player, pi.country, pi.gender,
                     SUM(b.wickets) AS total
              FROM bowling_innings b JOIN player_index pi USING (player_id)
              WHERE pi.player_id IN (SELECT player_id FROM active) {g} GROUP BY ALL)
        SELECT player, country, gender, total, (total // 50 + 1) * 50 AS target,
               (total // 50 + 1) * 50 - total AS needed, 'wickets' AS stat
        FROM t WHERE total >= 50 AND (total // 50 + 1) * 50 - total <= 5
        ORDER BY needed LIMIT {limit}"""
    out = []
    for sql in (runs_sql, wkts_sql):
        for r in _rows(db, sql, ps):
            caveat = (" Totals exclude Afghanistan matches Cricsheet withholds."
                      if r["country"] == "Afghanistan" else "")
            out.append({
                "kind": "milestone",
                "headline": f"{r['player']} needs {r['needed']} {r['stat']} for {r['target']:,} in T20Is",
                "detail": f"{r['country']} ({'men' if r['gender'] == 'male' else 'women'}): {r['total']:,} so far.{caveat}",
                "sql": " ".join(sql.split()),
            })
    return out


def team_streaks(db, min_len=4):
    sql = f"""
        WITH res AS (
            SELECT t.team, m.gender, m.date, m.match_id,
                   CASE WHEN m.winner = t.team THEN 'W' WHEN m.result = 'win' THEN 'L' ELSE 'X' END AS r
            FROM matches m, (SELECT unnest(?::VARCHAR[]) AS team) t
            WHERE t.team IN (m.team1, m.team2)),
        ordered AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY team, gender ORDER BY date DESC, match_id DESC) AS rn FROM res
                    WHERE r <> 'X'),
        firstbreak AS (SELECT team, gender, MIN(rn) FILTER (WHERE r <> first_r) AS brk, ANY_VALUE(first_r) AS first_r
                       FROM (SELECT *, FIRST_VALUE(r) OVER (PARTITION BY team, gender ORDER BY rn) AS first_r FROM ordered)
                       GROUP BY team, gender)
        SELECT f.team, f.gender, f.first_r AS kind, COALESCE(f.brk - 1, (SELECT COUNT(*) FROM ordered o
               WHERE o.team = f.team AND o.gender = f.gender)) AS length,
               (SELECT MAX(date) FROM ordered o WHERE o.team = f.team AND o.gender = f.gender) AS last_match
        FROM firstbreak f WHERE COALESCE(f.brk - 1, 0) >= {min_len} ORDER BY length DESC"""
    out = []
    for r in _rows(db, sql, [list(FULL_MEMBERS)]):
        word = "winning" if r["kind"] == "W" else "losing"
        out.append({
            "kind": "streak",
            "headline": f"{r['team']} {'men' if r['gender'] == 'male' else 'women'} are on a {r['length']}-match "
                        f"T20I {word} streak",
            "detail": f"Most recent result {r['last_match']}. Ties and no-results don't break or extend it.",
            "sql": " ".join(sql.split()),
        })
    return out


def stat_of_the_day(db, today=None):
    """On this day: the best innings and best bowling on today's date in past T20Is."""
    today = today or datetime.date.today()
    bat_sql = """
        SELECT COALESCE(pi.full_name, pi.name) AS player, b.team, b.runs, b.balls, m.date,
               CASE WHEN b.team = m.team1 THEN m.team2 ELSE m.team1 END AS opponent, m.gender, m.match_id
        FROM batting_innings b JOIN matches m USING (match_id) JOIN player_index pi USING (player_id)
        WHERE month(m.date) = ? AND day(m.date) = ? AND pi.gender = m.gender
        ORDER BY b.runs DESC, b.balls ASC LIMIT 1"""
    bowl_sql = """
        SELECT COALESCE(pi.full_name, pi.name) AS player, b.team, b.wickets, b.runs_conceded, m.date,
               CASE WHEN b.team = m.team1 THEN m.team2 ELSE m.team1 END AS opponent, m.gender, m.match_id
        FROM bowling_innings b JOIN matches m USING (match_id) JOIN player_index pi USING (player_id)
        WHERE month(m.date) = ? AND day(m.date) = ? AND pi.gender = m.gender
        ORDER BY b.wickets DESC, b.runs_conceded ASC LIMIT 1"""
    out = []
    p = [today.month, today.day]
    for r in _rows(db, bat_sql, p):
        out.append({"kind": "on_this_day", "match_id": r["match_id"],
                    "headline": f"On this day in {r['date'][:4]}: {r['player']} made {r['runs']} off {r['balls']} "
                                f"for {r['team']} v {r['opponent']}",
                    "detail": "Highest T20I score on this date.", "sql": " ".join(bat_sql.split())})
    for r in _rows(db, bowl_sql, p):
        out.append({"kind": "on_this_day", "match_id": r["match_id"],
                    "headline": f"On this day in {r['date'][:4]}: {r['player']} took {r['wickets']}/{r['runs_conceded']} "
                                f"for {r['team']} v {r['opponent']}",
                    "detail": "Best T20I bowling on this date.", "sql": " ".join(bowl_sql.split())})
    return out


def all_prompts(db, today=None):
    return {"stat_of_the_day": stat_of_the_day(db, today), "milestones": milestones(db),
            "streaks": team_streaks(db)}
