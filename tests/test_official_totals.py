"""Career T20I totals from the database vs official ESPNcricinfo figures (tests/official_figures.csv).

Run: .venv/bin/python -m pytest tests -v
Players whose gap is fully explained by matches missing from the source data are xfail(strict),
so the test starts failing loudly (XPASS) if the data is ever completed.
"""
import csv
from pathlib import Path

import sys
import pytest

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "wickets.duckdb"

# Gaps traced to matches absent from Cricsheet, not to ingestion logic.
KNOWN_GAPS = {
    "Jasprit Bumrah": "3 wkts in India v Afghanistan, Delhi, 13/15/17 Sep 2026 (withheld; see test_bumrah_match_by_match)",
    "Rashid Khan": "Afghanistan T20Is after 2024-06-26 not in any open snapshot",
    "Ellyse Perry": "early women's T20Is (2008-2013) without ball-by-ball records in Cricsheet",
    "Meg Lanning": "early women's T20Is (2010-2013) without ball-by-ball records in Cricsheet",
    "Smriti Mandhana": "women's T20Is 2013-2017 without ball-by-ball records in Cricsheet",
}


def official():
    with open(ROOT / "tests" / "official_figures.csv", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def con():
    # Share the app's locked-down connection: DuckDB refuses a second connection to the same file
    # in one process with different settings.
    sys.path.insert(0, str(ROOT))
    from wickets.db import Database
    return Database(DB).con


def career(con, cricinfo_id):
    return con.execute("""
        WITH p AS (SELECT player_id FROM players WHERE cricinfo_id = ?)
        SELECT
            (SELECT COALESCE(SUM(runs), 0) FROM batting_innings WHERE player_id = (SELECT player_id FROM p)),
            (SELECT COALESCE(SUM(wickets), 0) FROM bowling_innings WHERE player_id = (SELECT player_id FROM p))
    """, [cricinfo_id]).fetchone()


def params():
    for row in official():
        marks = [pytest.mark.xfail(reason=KNOWN_GAPS[row["player"]], strict=True)] if row["player"] in KNOWN_GAPS else []
        yield pytest.param(row, id=row["player"], marks=marks)


@pytest.mark.parametrize("row", list(params()))
def test_career_runs_and_wickets(con, row):
    runs, wickets = career(con, int(row["cricinfo_id"]))
    assert (runs, wickets) == (int(row["runs"]), int(row["wickets"]))


def test_every_match_has_deliveries(con):
    assert con.execute("""
        SELECT COUNT(*) FROM matches m
        WHERE NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.match_id = m.match_id)
    """).fetchone()[0] == 0


def test_no_innings_exceeds_twenty_legal_overs(con):
    # Over-length innings are allowed only where Cricsheet flags an umpire miscount (e.g. a 7-ball over).
    assert con.execute("""
        SELECT COUNT(*) FROM (
            SELECT match_id, innings, SUM(is_legal_ball::INT) AS legal FROM deliveries
            WHERE NOT is_super_over GROUP BY ALL HAVING legal > 120) x
        JOIN innings i USING (match_id, innings)
        WHERE i.miscounted_overs = 0
    """).fetchone()[0] == 0


def test_team_totals_add_up(con):
    # Sum of batter runs + extras must equal total runs on every ball.
    assert con.execute("""
        SELECT COUNT(*) FROM deliveries
        WHERE runs_batter + wides + noballs + byes + legbyes + penalty <> total_runs
    """).fetchone()[0] == 0


def test_phase_tagging(con):
    rows = dict(con.execute("SELECT phase, MIN(over) || '-' || MAX(over) FROM deliveries GROUP BY 1").fetchall())
    assert rows == {"powerplay": "0-5", "middle": "6-14", "death": "15-19"}


# Bumrah's 100 official T20Is (Statsguru innings list, 2026-10-25) vs the database, match by match.
BUMRAH_NOT_IN_DB = {
    1202242: "v Sri Lanka, Guwahati, 2020-01-05: abandoned without a ball, so no Cricsheet record",
    1549586: "v Afghanistan, Delhi, 2026-09-13: withheld by Cricsheet",
    1549587: "v Afghanistan, Delhi, 2026-09-15: withheld by Cricsheet",
    1549588: "v Afghanistan, Delhi, 2026-09-17: withheld by Cricsheet",
}


def test_bumrah_match_by_match(con):
    with open(ROOT / "tests" / "bumrah_official_innings.csv", newline="") as f:
        official = {int(r["match_id"]): (int(r["wickets"]) if r["wickets"] else None) for r in csv.DictReader(f)}
    db = dict(con.execute("""
        SELECT r.match_id, COALESCE(b.wickets, 0) FROM match_roles r
        JOIN players p ON p.player_id = r.player_id AND p.cricinfo_id = 625383
        LEFT JOIN (SELECT match_id, player_id, SUM(wickets) AS wickets FROM bowling_innings GROUP BY ALL) b
            ON b.match_id = r.match_id AND b.player_id = r.player_id
    """).fetchall())
    assert set(official) - set(db) == set(BUMRAH_NOT_IN_DB)
    assert set(db) <= set(official)
    assert {m: w for m, w in db.items() if (official[m] or 0) != w} == {}
