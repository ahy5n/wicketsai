"""Filter builder: structured filters -> deterministic SQL. No model involved, so no cost and no
interpretation risk; the same proof panel and coverage notes apply.

Perspectives:
  batting  a player's (or everyone's) batting, split by the filters
  bowling  a player's (or everyone's) bowling
"""
import re
from dataclasses import asdict

from . import proof

PHASES = {"powerplay", "middle", "death"}
BOWLING_KINDS = {"pace", "spin"}
BOWLING_TYPES = {"fast", "fast-medium", "medium-fast", "medium", "off-spin", "leg-spin", "orthodox", "wrist-spin"}
HANDS = {"left", "right"}
GROUPS = {
    "none": None, "year": "year(date)", "opponent": "{opp}", "phase": "phase", "bowling_type": "bowling_type",
    "batting_hand": "batter_hand", "venue": "venue_name",
}
PLAYER_ID = re.compile(r"^[0-9a-z]{8}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FilterError(ValueError):
    pass


def build(f):
    """-> (answer_sql, evidence_sql, params, description). Raises FilterError on bad input."""
    perspective = f.get("perspective", "batting")
    if perspective not in ("batting", "bowling"):
        raise FilterError("perspective must be batting or bowling")
    opp = "bowling_team" if perspective == "batting" else "batting_team"
    # Conditions are templates over {me} (the player's column) and {hand} (the batter's hand), so the
    # same filters can be applied to the balls a batter faced and to the wickets where they were out
    # (a run-out at the non-striker's end falls on a ball someone else faced).
    conds, desc = [("NOT d.is_super_over", [])], []

    def add(cond, *vals):
        conds.append((cond, list(vals)))

    if f.get("player_id"):
        if not PLAYER_ID.match(f["player_id"]):
            raise FilterError("bad player_id")
        add("{me} = ?", f["player_id"])
    if f.get("gender"):
        if f["gender"] not in ("male", "female"):
            raise FilterError("gender must be male or female")
        add("d.gender = ?", f["gender"])
        desc.append("men's" if f["gender"] == "male" else "women's")
    if f.get("opponent"):
        add(f"d.{opp} = ?", f["opponent"])
        desc.append(f"v {f['opponent']}")
    if f.get("venue_id") is not None:
        add("d.venue_id = ?", int(f["venue_id"]))
    for key, op in (("date_from", ">="), ("date_to", "<=")):
        if f.get(key):
            if not DATE.match(f[key]):
                raise FilterError(f"{key} must be YYYY-MM-DD")
            add(f"d.date {op} CAST(? AS DATE)", f[key])
    if f.get("phases"):
        phases = set(f["phases"])
        if not phases <= PHASES:
            raise FilterError("unknown phase")
        add(f"d.phase IN ({','.join('?' * len(phases))})", *sorted(phases))
        desc.append("/".join(sorted(phases)))
    if f.get("bowling_kind"):
        if f["bowling_kind"] not in BOWLING_KINDS:
            raise FilterError("bowling_kind must be pace or spin")
        add("d.bowling_kind = ?", f["bowling_kind"])
        desc.append(f"v {f['bowling_kind']}")
    if f.get("bowling_type"):
        if f["bowling_type"] not in BOWLING_TYPES:
            raise FilterError("unknown bowling_type")
        add("d.bowling_type = ?", f["bowling_type"])
        desc.append(f"v {f['bowling_type']}")
    if f.get("batting_hand"):
        if f["batting_hand"] not in HANDS:
            raise FilterError("batting_hand must be left or right")
        add("{hand} = ?", f["batting_hand"])
        desc.append(f"{f['batting_hand']}-handed batters")
    pos = None
    if f.get("batting_position"):
        pos = int(f["batting_position"])
        if not 1 <= pos <= 11:
            raise FilterError("batting_position must be 1-11")
        add("r.batting_position = ?", pos)
        desc.append(f"batting at {pos}")

    group = f.get("group_by", "none")
    if group not in GROUPS:
        raise FilterError("unknown group_by")
    gexpr = {"year": "year(d.date)", "opponent": f"d.{opp}", "phase": "d.phase", "bowling_type": "d.bowling_type",
             "batting_hand": "{hand}", "venue": "v.name"}.get(group)

    def where(me, hand):
        sql = " AND ".join(c.format(me=me, hand=hand) for c, _ in conds)
        return sql, [v for _, vals in conds for v in vals]

    def source(me, hand, extra_join=""):
        joins = f"JOIN venues v ON v.venue_id = d.venue_id {extra_join}"
        if pos:
            joins += f" JOIN match_roles r ON r.match_id = d.match_id AND r.player_id = {me}"
        w, ps = where(me, hand)
        return f"FROM deliveries_ctx d {joins} WHERE {w}", ps

    key = f"{gexpr.format(hand='d.batter_hand')} AS g" if gexpr else "1 AS g"
    if perspective == "batting":
        balls_from, balls_params = source("d.batter_id", "d.batter_hand")
        outs_from, outs_params = source(
            "w.player_out_id", "ph.batting_hand",
            "JOIN wickets w ON w.match_id = d.match_id AND w.innings = d.innings AND w.over = d.over "
            "AND w.ball = d.ball JOIN players ph ON ph.player_id = w.player_out_id")
        okey = f"{gexpr.format(hand='ph.batting_hand')} AS g" if gexpr else "1 AS g"
        sql = (f"WITH b AS (SELECT {key}, COUNT(DISTINCT d.match_id) AS matches, SUM(d.runs_batter) AS runs, "
               f"SUM(d.is_ball_faced::INT) AS balls, SUM(d.is_four::INT) AS fours, SUM(d.is_six::INT) AS sixes, "
               f"SUM(CASE WHEN d.is_ball_faced AND d.runs_batter = 0 THEN 1 ELSE 0 END) AS dots "
               f"{balls_from} GROUP BY 1), "
               f"o AS (SELECT {okey}, COUNT(*) AS dismissals {outs_from} "
               f"AND w.kind NOT IN ('retired hurt', 'retired not out') GROUP BY 1) "
               f"SELECT {'b.g AS ' + group + ', ' if gexpr else ''}b.matches, b.runs, b.balls, "
               f"ROUND(100.0 * b.runs / NULLIF(b.balls, 0), 2) AS strike_rate, COALESCE(o.dismissals, 0) AS dismissals, "
               f"ROUND(b.runs / NULLIF(o.dismissals, 0), 2) AS average, b.fours, b.sixes, "
               f"ROUND(100.0 * b.dots / NULLIF(b.balls, 0), 1) AS dot_pct "
               f"FROM b LEFT JOIN o ON o.g IS NOT DISTINCT FROM b.g ORDER BY 1")
        params = balls_params + outs_params
        ev_from, ev_params = balls_from, balls_params
    else:
        balls_from, params = source("d.bowler_id", "d.batter_hand")
        sql = (f"SELECT {'g AS ' + group + ', ' if gexpr else ''}matches, overs, runs, wickets, economy, average, "
               f"strike_rate, dot_pct FROM (SELECT {key}, COUNT(DISTINCT d.match_id) AS matches, "
               f"(SUM(d.is_legal_ball::INT) // 6) || '.' || (SUM(d.is_legal_ball::INT) % 6) AS overs, "
               f"SUM(d.runs_conceded) AS runs, SUM(d.is_bowler_wkt::INT) AS wickets, "
               f"ROUND(SUM(d.runs_conceded) / NULLIF(SUM(d.is_legal_ball::INT) / 6.0, 0), 2) AS economy, "
               f"ROUND(SUM(d.runs_conceded) / NULLIF(SUM(d.is_bowler_wkt::INT), 0), 2) AS average, "
               f"ROUND(SUM(d.is_legal_ball::INT) / NULLIF(SUM(d.is_bowler_wkt::INT), 0), 1) AS strike_rate, "
               f"ROUND(100.0 * SUM(d.is_dot::INT) / NULLIF(SUM(d.is_legal_ball::INT), 0), 1) AS dot_pct "
               f"{balls_from} GROUP BY 1) ORDER BY 1")
        ev_from, ev_params = balls_from, params
    evidence_sql = f"SELECT d.match_id, COUNT(*) AS balls {ev_from} GROUP BY d.match_id"
    return sql, evidence_sql, (params, ev_params), ", ".join(desc)


def run(db, f, latest_date=None):
    """Run a filter query and return an Answer-shaped dict (same shape as engine answers)."""
    answer_sql, evidence_sql, (params, ev_params), desc = build(f)
    table = db.query(answer_sql, max_rows=200, params=params)
    ev = db.query(evidence_sql, max_rows=100_000, params=ev_params)
    match_ids = [r[0] for r in ev.rows]
    balls = int(sum(r[1] for r in ev.rows))
    evidence, match_rows = proof.build_evidence(db, match_ids, balls)
    who = ""
    if f.get("player_id"):
        row = db.query("SELECT COALESCE(full_name, name) FROM player_index WHERE player_id = ?",
                       params=[f["player_id"]]).rows
        who = row[0][0] if row else f["player_id"]
    title = " ".join(x for x in [who, f.get("perspective", "batting"), desc and f"({desc})"] if x)
    # inline the bound values so the proof panel shows a runnable query
    shown = answer_sql
    for p in params:
        shown = shown.replace("?", f"'{p}'" if isinstance(p, str) else str(p), 1)
    return {
        "question": title, "can_answer": bool(match_ids),
        "answer": (f"{title}: {evidence.match_count:,} matches, {balls:,} balls." if match_ids
                   else "No deliveries match those filters."),
        "display": "table" if f.get("group_by", "none") != "none" else "sentence",
        "table": {"columns": table.columns, "rows": table.rows, "truncated": table.truncated},
        "sql": shown, "evidence": asdict(evidence), "assumptions": [],
        "coverage_notes": proof.coverage_notes(match_rows, answer_sql, title, latest_date),
        "trace": [], "usage": {"usd": 0}, "error": None, "filters": f,
    }
