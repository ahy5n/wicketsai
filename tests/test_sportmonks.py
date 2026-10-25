"""Sportmonks -> Cricsheet converter, checked on the sample fixture from Sportmonks' public API docs
(BBL, Brisbane Heat v Melbourne Stars, 2021-01-07; Cricsheet match 1226835)."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
import sportmonks  # noqa: E402


def converted():
    fx = json.loads((ROOT / "tests" / "fixtures" / "sportmonks_sample_fixture_21897.json").read_text())["data"]
    teams = {b["team_id"]: b["team"]["name"] for b in fx["balls"]}
    known = {b[k]["id"] for b in fx["balls"] for k in ("batsman", "bowler")}
    fx["lineup"] = []
    for b in fx["balls"]:  # fielders appear only as ids in the sample
        for k in ("catchstump_id", "batsmanout_id", "batsman_one_on_creeze_id", "batsman_two_on_creeze_id"):
            if b.get(k) and b[k] not in known:
                known.add(b[k])
                fx["lineup"].append({"id": b[k], "fullname": f"id{b[k]}", "lineup": {"team_id": None}})
    teams[None] = None
    return sportmonks.convert_fixture(fx, teams, lambda team, p: (p["fullname"], str(p["id"])))


def test_innings_totals_and_shape():
    m = converted()
    totals = [sum(d["runs"]["total"] for o in i["overs"] for d in o["deliveries"]) for i in m["innings"]]
    # Cricsheet has 111 for the chase: Sportmonks scores ball 9.6 (Gotch off Bartlett) as a dot, Cricsheet as 1.
    assert totals == [115, 110]
    assert [i["team"] for i in m["innings"]] == ["Brisbane Heat", "Melbourne Stars"]
    assert [sum(len(o["deliveries"]) for o in i["overs"]) for i in m["innings"]] == [63, 61]


def test_dismissals_and_extras():
    m = converted()
    kinds = Counter(w["kind"] for i in m["innings"] for o in i["overs"] for d in o["deliveries"] for w in d.get("wickets", []))
    extras = Counter()
    for i in m["innings"]:
        for o in i["overs"]:
            for d in o["deliveries"]:
                extras.update(d.get("extras", {}))
    assert kinds == {"caught": 6, "lbw": 1, "bowled": 1}
    assert extras == {"legbyes": 3, "wides": 2, "noballs": 2}


def test_every_runs_total_adds_up():
    m = converted()
    for i in m["innings"]:
        for o in i["overs"]:
            for d in o["deliveries"]:
                assert d["runs"]["batter"] + d["runs"]["extras"] == d["runs"]["total"]
