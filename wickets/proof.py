"""Proof panel: the matches behind an answer, links to them, and coverage gaps that touch it.

Coverage notes are computed here from the matches an answer used, not left to the model, so a gap
can't be forgotten.
"""
import csv
import datetime
import re
from dataclasses import dataclass, field

from .db import ROOT

MATCH_URL = "https://www.espncricinfo.com/matches/engine/match/{}.html"
AFG_CUTOFF = datetime.date(2024, 6, 26)
WOMENS_PATCHY_BEFORE = datetime.date(2017, 1, 1)
PROFILE_COLUMNS = re.compile(r"\b(bowling_kind|bowling_type|bowling_arm|bowling_style|batter_hand|batting_hand)\b")


@dataclass
class Evidence:
    match_count: int = 0
    balls: int = None
    matches: list = field(default_factory=list)  # first N: id, date, fixture, url
    first_date: str = None
    last_date: str = None


def missing_afghanistan_matches():
    with open(ROOT / "data" / "afghanistan_t20is_missing.csv", newline="") as f:
        return [r for r in csv.DictReader(f) if r["afghanistan_result"] != "aban"]


def build_evidence(db, match_ids, balls=None, limit=50):
    ev = Evidence(match_count=len(match_ids), balls=balls)
    if not match_ids:
        return ev, []
    ids = ",".join(str(int(m)) for m in match_ids)
    rows = db.query(f"""
        SELECT match_id, date, gender, team1, team2, event_name FROM matches
        WHERE match_id IN ({ids}) ORDER BY date DESC
    """, max_rows=len(match_ids) + 1).as_dicts()
    ev.matches = [{
        "match_id": r["match_id"], "date": r["date"],
        "fixture": f"{r['team1']} v {r['team2']}", "event": r["event_name"],
        "url": MATCH_URL.format(r["match_id"]),
    } for r in rows[:limit]]
    if rows:
        ev.first_date, ev.last_date = rows[-1]["date"], rows[0]["date"]
    return ev, rows


def coverage_notes(match_rows, sql, question, latest_date=None):
    """Gaps that could change this answer, judged from the matches it used."""
    notes = []
    text = f"{question}\n{sql}".lower()
    date = datetime.date.fromisoformat
    latest_date = latest_date or datetime.date.today()

    men = [r for r in match_rows if r["gender"] == "male"]
    missing = missing_afghanistan_matches()
    if men:
        first = min(date(r["date"]) for r in men)
        last = max(date(r["date"]) for r in men)
        # Whose record is this? Teams in nearly every match used (a player's or a team's record).
        counts = {}
        for r in men:
            for t in {r["team1"], r["team2"]}:
                counts[t] = counts.get(t, 0) + 1
        core = {t for t, n in counts.items() if n >= 0.8 * len(men)}
        # Missing matches can't appear in the evidence, so an open-ended record (one running up to the
        # latest data, or Afghanistan's own, which stops at the cutoff) extends to today.
        open_ended = "Afghanistan" in core or (latest_date - last).days <= 60
        end = datetime.date.today() if open_ended else last
        in_window = [m for m in missing if first <= date(m["date"]) <= end]
        if "Afghanistan" in core or not core:
            relevant = in_window  # Afghanistan's own record, or a broad all-teams question
        else:
            relevant = [m for m in in_window if _alias(m["opponent"]) in core]
        if relevant:
            opps = sorted({_alias(m["opponent"]) for m in relevant})
            dates = sorted(m["date"] for m in relevant)
            span = dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}"
            who = "Afghanistan" if ("Afghanistan" in core or not core) else " / ".join(sorted(core))
            notes.append(
                f"{len(relevant)} {who} T20I(s) against {'Afghanistan' if who != 'Afghanistan' else ', '.join(opps)} "
                f"({span}) are not in the database (Cricsheet withholds Afghanistan matches)"
                + ("." if who == "Afghanistan" else "; anyone who played in them is missing those games."))
    elif "afghanistan" in text:
        notes.append(f"The {len(missing)} Afghanistan men's T20Is played after 26 Jun 2024 are not in the database "
                     "(Cricsheet withholds them).")

    women = [r for r in match_rows if r["gender"] == "female"]
    if women and min(date(r["date"]) for r in women) < WOMENS_PATCHY_BEFORE:
        notes.append("Women's T20I ball-by-ball records are incomplete before 2017 (badly so before 2014, and "
                     "none exist before June 2009), so figures for players active then are understated.")

    if PROFILE_COLUMNS.search(sql or ""):
        notes.append("Bowling type and batting hand come from player profiles (Wikipedia); some players, mostly "
                     "from Associate nations, have no profile and are left out of type/hand splits.")
    return notes


def _alias(team):
    return {"U.A.E.": "United Arab Emirates", "U.S.A.": "United States of America"}.get(team, team)
