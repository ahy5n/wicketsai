"""Fill the Afghanistan T20Is Cricsheet never published (after 2024-06-26) from the Sportmonks Cricket API.

Needs a Sportmonks API token with T20I coverage (league 3, "Twenty20 International"):
    export SPORTMONKS_API_TOKEN=...
    python ingest/sportmonks.py         # fetch + convert into data/raw/sportmonks/<cricinfo_id>.json
    python ingest/ingest.py             # rebuild; the files are loaded with source='sportmonks'

Targets come from data/afghanistan_t20is_missing.csv (Cricinfo match ids, dates, opponents); each
Sportmonks fixture is matched on date + opponent and written under the Cricinfo id so match links stay
consistent. Output is Cricsheet JSON 1.x shaped, so ingest.parse_match needs no changes.
"""
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = RAW / "sportmonks"
API = "https://cricket.sportmonks.com/api/v2.0"
T20I_LEAGUE = 3
TEAM_ALIASES = {"U.A.E.": "United Arab Emirates", "U.S.A.": "United States of America"}

# Sportmonks score names -> Cricsheet dismissal kinds. Anything with is_wicket but not listed is an error.
KINDS = [
    (r"obstruct", "obstructing the field"),
    (r"hit the ball twice", "hit the ball twice"),
    (r"hit wicket", "hit wicket"),
    (r"stump", "stumped"),
    (r"run out", "run out"),
    (r"lbw", "lbw"),
    (r"bowled", "bowled"),
    (r"catch", "caught"),
    (r"retired out", "retired out"),
    (r"retired hurt", "retired hurt"),
    (r"absent", "retired not out"),
]


def get(path, **params):
    token = os.environ["SPORTMONKS_API_TOKEN"]
    url = f"{API}/{path}?" + urllib.parse.urlencode({**params, "api_token": token})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Sportmonks request failed: {path}")


def dismissal_kind(score, catcher_id, bowler_id):
    name = score["name"].lower()
    for pat, kind in KINDS:
        if re.search(pat, name):
            if kind == "caught" and catcher_id and catcher_id == bowler_id:
                return "caught and bowled"
            return kind
    raise ValueError(f"unmapped Sportmonks dismissal: {score['name']!r}")


def convert_ball(b, name_of):
    """One Sportmonks ball -> one Cricsheet delivery dict."""
    s = b["score"]
    total_runs = s["runs"]
    bye, leg_bye = s["bye"], s["leg_bye"]
    wide = not s["ball"] and "wide" in s["name"].lower()
    penalty = 5 if "pen" in s["name"].lower() else 0
    extras = {}
    if wide:
        # 'runs' on a wide is the wide penalty plus any runs taken; byes off a wide are listed separately.
        extras["wides"] = total_runs
        if bye:
            extras["wides"] += bye
        batter_runs = 0
    elif s["noball"]:
        nb_extra = s["noball_runs"] or 1
        extras["noballs"] = nb_extra
        if bye:
            extras["byes"] = bye
        if leg_bye:
            extras["legbyes"] = leg_bye
        batter_runs = max(total_runs - nb_extra, 0)
    else:
        if bye:
            extras["byes"] = bye
        if leg_bye:
            extras["legbyes"] = leg_bye
        batter_runs = total_runs
    if penalty:
        extras["penalty"] = penalty
    extras_total = sum(extras.values())

    striker = b["batsman_id"]
    pair = {b.get("batsman_one_on_creeze_id"), b.get("batsman_two_on_creeze_id")} - {striker, None}
    non_striker = next(iter(pair), None)
    d = {
        "batter": name_of(striker),
        "bowler": name_of(b["bowler_id"]),
        "non_striker": name_of(non_striker) if non_striker else name_of(striker),
        "runs": {"batter": batter_runs, "extras": extras_total, "total": batter_runs + extras_total},
    }
    if batter_runs in (4, 6) and not (s["four"] or s["six"]):
        d["runs"]["non_boundary"] = True
    if extras:
        d["extras"] = extras
    if s["is_wicket"] or s["out"]:
        kind = dismissal_kind(s, b.get("catchstump_id"), b["bowler_id"])
        out_id = b.get("batsmanout_id") or striker
        w = {"player_out": name_of(out_id), "kind": kind}
        fielder = b.get("catchstump_id") or b.get("runout_by_id")
        if fielder and kind in ("caught", "stumped", "run out"):
            w["fielders"] = [{"name": name_of(fielder)}]
        d["wickets"] = [w]
    return d


def convert_fixture(fx, teams, registry_for):
    """Sportmonks fixture (include=balls,lineup,venue,tosswon) -> Cricsheet-shaped match dict.

    teams: {sportmonks_team_id: team name}. registry_for(team, sm_player) -> (name, cricsheet_id).
    """
    players, people = {}, {}
    sm_team = {p["id"]: p["lineup"]["team_id"] for p in fx.get("lineup", [])}
    for p in fx.get("lineup", []):
        team = teams[p["lineup"]["team_id"]]
        name, pid = registry_for(team, p)
        players.setdefault(team, []).append(name)
        people[name] = pid

    by_id = {p["id"]: p for p in fx.get("lineup", [])}
    for b in fx["balls"]:  # players missing from the lineup (concussion subs etc.)
        for k in ("batsman", "bowler"):
            if b.get(k) and b[k]["id"] not in by_id:
                by_id[b[k]["id"]] = b[k]

    def name_of(sm_id):
        if sm_id not in by_id:
            raise ValueError(f"player {sm_id} not in lineup or balls")
        p = by_id[sm_id]
        team = teams.get(sm_team.get(sm_id)) or teams.get(p.get("lineup", {}).get("team_id"))
        name, pid = registry_for(team, p)
        people[name] = pid
        return name

    innings = []
    for sb in sorted({b["scoreboard"] for b in fx["balls"]}, key=lambda s: int(s[1:])):
        balls = [b for b in fx["balls"] if b["scoreboard"] == sb]
        balls.sort(key=lambda b: b["id"])  # ball ids increase in bowling order; 0.10 == 0.1 as a float
        overs = {}
        for b in balls:
            overs.setdefault(int(b["ball"]), []).append(convert_ball(b, name_of))
        inn = {"team": teams[balls[0]["team_id"]],
               "overs": [{"over": o, "deliveries": ds} for o, ds in sorted(overs.items())]}
        if int(sb[1:]) > 2:
            inn["super_over"] = True
        innings.append(inn)

    winner = teams.get(fx.get("winner_team_id"))
    by = {}
    m = re.search(r"won by (\d+) (runs?|wickets?)", fx.get("note") or "")
    if m:
        by = {"runs" if m.group(2).startswith("run") else "wickets": int(m.group(1))}
    outcome = {"winner": winner, "by": by} if winner else {"result": "tie" if "tie" in (fx.get("note") or "").lower() else "no result"}
    if fx.get("note") and "D/L" in fx["note"]:
        outcome["method"] = "D/L"
    venue = fx.get("venue") or {}
    return {
        "meta": {"data_version": "1.1.0", "source": "sportmonks", "sportmonks_fixture_id": fx["id"]},
        "info": {
            "balls_per_over": 6,
            "dates": [fx["starting_at"][:10]],
            "gender": "male",
            "match_type": "T20",
            "overs": 20,
            "teams": [teams[fx["localteam_id"]], teams[fx["visitorteam_id"]]],
            "toss": {"winner": teams.get(fx.get("toss_won_team_id")),
                     "decision": "field" if fx.get("elected") == "bowling" else "bat"},
            "outcome": outcome,
            "venue": venue.get("name") or "Unknown",
            "city": venue.get("city"),
            "event": {"name": (fx.get("stage") or {}).get("name") or fx.get("round")},
            "players": players,
            "registry": {"people": people},
        },
        "innings": innings,
    }


class Registry:
    """Map Sportmonks players onto Cricsheet register ids by team + surname + first initial."""

    def __init__(self, db_path):
        import duckdb
        con = duckdb.connect(str(db_path), read_only=True)
        rows = con.execute("""
            SELECT DISTINCT r.team, p.player_id, p.name, p.unique_name
            FROM match_roles r JOIN players p USING (player_id)
        """).fetchall()
        con.close()
        self.by_team = {}
        for team, pid, name, uname in rows:
            self.by_team.setdefault(team, []).append((pid, name or uname))
        self.cache = {}

    @staticmethod
    def _key(fullname):
        parts = re.sub(r"[^A-Za-z ]", " ", fullname).split()
        return (parts[-1].lower(), parts[0][0].lower()) if parts else ("", "")

    def __call__(self, team, p):
        if p["id"] in self.cache:
            return self.cache[p["id"]]
        full = p["fullname"]
        exact = [(pid, n) for pid, n in self.by_team.get(team, []) if n == full]
        surname, initial = self._key(full)
        loose = [(pid, n) for pid, n in self.by_team.get(team, [])
                 if n.split()[-1].lower() == surname and n[0].lower() == initial]
        hit = exact or (loose if len(loose) == 1 else [])
        result = (hit[0][1], hit[0][0]) if hit else (full, f"sm{p['id']}")  # new player: Sportmonks id
        self.cache[p["id"]] = result
        return result


def load_dotenv():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() and v.strip() and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main():
    load_dotenv()
    if not os.environ.get("SPORTMONKS_API_TOKEN"):
        sys.exit("Set SPORTMONKS_API_TOKEN in the environment or in .env (a Sportmonks cricket plan that includes T20Is).")
    OUT.mkdir(parents=True, exist_ok=True)
    targets = list(csv.DictReader(open(ROOT / "data" / "afghanistan_t20is_missing.csv")))
    teams = {t["id"]: t["name"] for t in get("teams", **{"filter[national_team]": "true"})["data"]}
    afg = next(i for i, n in teams.items() if n == "Afghanistan")
    reg = Registry(ROOT / "data" / "wickets.duckdb")

    found = 0
    for t in targets:
        opp = TEAM_ALIASES.get(t["opponent"], t["opponent"])
        fixtures = get("fixtures", **{
            "filter[league_id]": T20I_LEAGUE,
            "filter[starts_between]": f"{t['date']},{t['date']}",
        })["data"]
        fx = next((f for f in fixtures if afg in (f["localteam_id"], f["visitorteam_id"])
                   and opp in (teams.get(f["localteam_id"]), teams.get(f["visitorteam_id"]))), None)
        if not fx:
            print(f"  not found: {t['date']} v {opp}")
            continue
        full = get(f"fixtures/{fx['id']}", include="balls,lineup,venue,stage")["data"]
        if not full.get("balls"):
            print(f"  no balls:  {t['date']} v {opp} (fixture {fx['id']})")
            continue
        match = convert_fixture(full, teams, reg)
        match["info"]["match_type_number"] = None
        (OUT / f"{t['match_id']}.json").write_text(json.dumps(match))
        found += 1
        print(f"  ok:        {t['date']} v {opp} ({len(full['balls'])} balls)")
    print(f"{found}/{len(targets)} fixtures written to {OUT}")


if __name__ == "__main__":
    main()
