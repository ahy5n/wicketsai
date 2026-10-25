"""Load Cricsheet men's and women's T20I JSON into DuckDB.

Usage:
    python ingest/ingest.py            # download (if needed) and rebuild data/wickets.duckdb
    python ingest/ingest.py --refresh  # re-download the zip and register first

Re-runnable: the database is rebuilt from scratch each time.
"""
import argparse
import collections
import csv
import json
import os
import re
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import duckdb

import legacy_yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "wickets.duckdb"
ZIP_URL = "https://cricsheet.org/downloads/t20s_json.zip"
PEOPLE_URL = "https://cricsheet.org/register/people.csv"
# Cricsheet withholds Afghanistan men's matches (since early Dec 2024). The Wayback Machine copy of
# t20s_male.zip from 2024-10-09 (still ODC-BY) is the last snapshot before that and restores every
# Afghanistan T20I up to 2024-06-26. Later ones were never published by Cricsheet.
ARCHIVES = [
    {   # men's T20Is in legacy YAML, archived 2024-10-09
        "url": "https://web.archive.org/web/20241009231706id_/https://cricsheet.org/downloads/t20s_male.zip",
        "zip": RAW / "archive_2024" / "t20s_male_20241009.zip",
        "dir": RAW / "archive_2024" / "afg_t20i",
        "source": "cricsheet-archive-2024-10-09",
        "ext": ".yaml",
    },
]

# ICC: dismissals credited to the bowler.
BOWLER_WICKETS = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}


def download(refresh):
    RAW.mkdir(parents=True, exist_ok=True)
    for url, dest in [(ZIP_URL, RAW / "t20s_json.zip"), (PEOPLE_URL, RAW / "people.csv")]:
        if refresh or not dest.exists():
            print(f"downloading {url}")
            urllib.request.urlretrieve(url, dest)
    with zipfile.ZipFile(RAW / "t20s_json.zip") as z:
        z.extractall(RAW / "t20s")

    for a in ARCHIVES:
        if not a["zip"].exists():
            a["zip"].parent.mkdir(parents=True, exist_ok=True)
            print(f"downloading {a['url']}")
            urllib.request.urlretrieve(a["url"], a["zip"])
        a["dir"].mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(a["zip"]) as z:
            for line in z.read("README.txt").decode().replace("\r", "").splitlines():
                parts = line.split(" - ")
                if len(parts) > 5 and parts[1:3] == ["international", "T20"] and "Afghanistan" in parts[5]:
                    mid = parts[4].strip()
                    raw = z.read(mid + a["ext"])
                    d = legacy_yaml.load(raw) if a["ext"] == ".yaml" else json.loads(raw)
                    (a["dir"] / f"{mid}.json").write_text(json.dumps(d, default=str))  # YAML parses dates


def phase_of(over):
    if over < 6:
        return "powerplay"
    if over < 15:
        return "middle"
    return "death"


def powerplay_ranges(inn):
    return [(p["from"], p["to"]) for p in inn.get("powerplays", []) if p.get("type") == "mandatory"]


def split_venue(raw, city):
    """'Eden Gardens, Kolkata' -> 'Eden Gardens' when the suffix is the city."""
    if city and raw.endswith(", " + city):
        return raw[: -len(", " + city)]
    return raw


def parse_match(path, source, rows, venue_seen, team_counts):
    d = json.loads(path.read_text())
    info = d["info"]
    match_id = int(path.stem)
    registry = info["registry"]["people"]
    pid = lambda name: registry.get(name)

    outcome = info.get("outcome", {})
    by = outcome.get("by", {})
    result = outcome.get("result") or ("win" if outcome.get("winner") else None)
    decided_by = outcome.get("method")
    winner = outcome.get("winner")
    if outcome.get("eliminator"):
        winner, decided_by = outcome["eliminator"], "super over"
    if outcome.get("bowl_out"):
        winner, decided_by = outcome["bowl_out"], "bowl out"

    city = info.get("city")
    venue_name = split_venue(info["venue"], city)
    venue_seen[(venue_name, city)].add(info["venue"])

    teams = info["teams"]
    event = info.get("event", {})
    rows["matches"].append({
        "match_id": match_id,
        "t20i_number": info.get("match_type_number"),
        "gender": info["gender"],
        "date": info["dates"][0],
        "season": str(info.get("season")),
        "venue_key": f"{venue_name}|{city}",
        "venue_raw": info["venue"],
        "city": city,
        "team1": teams[0],
        "team2": teams[1],
        "toss_winner": info.get("toss", {}).get("winner"),
        "toss_decision": info.get("toss", {}).get("decision"),
        "winner": winner,
        "result": result,
        "win_by_runs": by.get("runs"),
        "win_by_wickets": by.get("wickets"),
        "decided_by": decided_by,
        "player_of_match": info.get("player_of_match", []),
        "event_name": event.get("name"),
        "event_match_no": str(event.get("match_number") or event.get("stage") or "") or None,
        "overs_per_side": info.get("overs"),
        "balls_per_over": info.get("balls_per_over", 6),
        "source": source,
    })

    for team, names in info["players"].items():
        for n in names:
            team_counts[pid(n)][team] += 1

    bat_order = collections.defaultdict(dict)  # team -> {player_id: position}
    for i, inn in enumerate(d["innings"], start=1):
        bat_team = inn["team"]
        bowl_team = teams[1] if bat_team == teams[0] else teams[0]
        super_over = bool(inn.get("super_over"))
        target = inn.get("target", {})
        pen = inn.get("penalty_runs", {})
        rows["innings"].append({
            "match_id": match_id, "innings": i, "batting_team": bat_team, "bowling_team": bowl_team,
            "is_super_over": super_over, "target_runs": target.get("runs"), "target_overs": target.get("overs"),
            "penalty_runs_pre": pen.get("pre"), "penalty_runs_post": pen.get("post"),
            "miscounted_overs": len(inn.get("miscounted_overs", {})),
        })
        pp = powerplay_ranges(inn)
        order = bat_order[bat_team]
        for ov in inn["overs"]:
            over = ov["over"]
            legal_so_far = 0
            for seq, b in enumerate(ov["deliveries"], start=1):
                ex = b.get("extras", {})
                runs = b["runs"]
                wides, noballs = ex.get("wides", 0), ex.get("noballs", 0)
                byes, legbyes, penalty = ex.get("byes", 0), ex.get("legbyes", 0), ex.get("penalty", 0)
                legal = wides == 0 and noballs == 0
                ball_no = legal_so_far + 1  # Cricsheet's over.ball notation counts legal balls only
                if legal:
                    legal_so_far += 1
                in_pp = any(lo <= over + ball_no / 10 <= hi + 1e-9 for lo, hi in pp) if not super_over else False

                batter, non_striker, bowler = pid(b["batter"]), pid(b["non_striker"]), pid(b["bowler"])
                if not super_over:
                    for p in (batter, non_striker):
                        if p not in order:
                            order[p] = len(order) + 1

                wkts = b.get("wickets", [])
                for w in wkts:
                    rows["wickets"].append({
                        "match_id": match_id, "innings": i, "over": over, "ball": seq,
                        "player_out_id": pid(w["player_out"]), "kind": w["kind"], "bowler_id": bowler,
                        "fielder_ids": [pid(f["name"]) or f["name"] for f in w.get("fielders", []) if "name" in f],
                        "is_bowler_wkt": w["kind"] in BOWLER_WICKETS,
                    })
                first = wkts[0] if wkts else None
                conceded = runs["total"] - byes - legbyes - penalty
                non_boundary = bool(runs.get("non_boundary"))
                rows["deliveries"].append({
                    "match_id": match_id, "innings": i, "over": over, "ball": seq,
                    "batting_team": bat_team, "bowling_team": bowl_team,
                    "batter_id": batter, "non_striker_id": non_striker, "bowler_id": bowler,
                    "runs_batter": runs["batter"], "extras": runs["extras"],
                    "wides": wides, "noballs": noballs, "byes": byes, "legbyes": legbyes, "penalty": penalty,
                    "total_runs": runs["total"], "non_boundary": non_boundary,
                    "wicket_kind": first["kind"] if first else None,
                    "player_out_id": pid(first["player_out"]) if first else None,
                    "is_legal_ball": legal,
                    "is_ball_faced": wides == 0,
                    "runs_conceded": conceded,
                    "is_bowler_wkt": any(w["kind"] in BOWLER_WICKETS for w in wkts),
                    "is_four": runs["batter"] == 4 and not non_boundary,
                    "is_six": runs["batter"] == 6 and not non_boundary,
                    "is_dot": legal and runs["batter"] == 0 and conceded == 0,
                    "phase": phase_of(over),
                    "in_powerplay": in_pp,
                    "is_super_over": super_over,
                })

    for team, names in info["players"].items():
        order = bat_order.get(team, {})
        for n in names:
            p = pid(n)
            rows["match_roles"].append({
                "match_id": match_id, "player_id": p, "team": team,
                "batting_position": order.get(p), "captain": None, "wicketkeeper": None,
            })


def write_ndjson(rows, tmp):
    paths = {}
    for table, recs in rows.items():
        p = Path(tmp) / f"{table}.ndjson"
        with p.open("w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        paths[table] = p
    return paths


def build(con, rows, venue_seen, team_counts):
    con.execute((ROOT / "ingest" / "schema.sql").read_text())

    venue_keys = {}
    for vid, ((name, city), aliases) in enumerate(sorted(venue_seen.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")), 1):
        venue_keys[f"{name}|{city}"] = vid
        con.execute("INSERT INTO venues VALUES (?, ?, ?, NULL, ?)", [vid, name, city, sorted(aliases)])
    for m in rows["matches"]:
        m["venue_id"] = venue_keys[m.pop("venue_key")]

    people = {}
    with open(RAW / "people.csv", newline="") as f:
        for r in csv.DictReader(f):
            people[r["identifier"]] = r
    for p, teams in team_counts.items():
        r = people.get(p, {})
        ci = r.get("key_cricinfo")
        rows["players"].append({
            "player_id": p, "name": r.get("name"), "unique_name": r.get("unique_name"),
            "cricinfo_id": int(ci) if ci else None, "country": teams.most_common(1)[0][0],
        })

    with tempfile.TemporaryDirectory() as tmp:
        for table, path in write_ndjson(rows, tmp).items():
            con.execute(
                f"INSERT INTO {table} BY NAME SELECT * FROM read_json('{path}', format='newline_delimited', "
                f"maximum_object_size=1048576, sample_size=-1)"
            )

    readme = (RAW / "t20s" / "README.txt").read_text()
    withheld = re.search(r"A further (\d+) matches have been withheld[^.]*\.[^.]*\.", readme.replace("\n", " "))
    if withheld:
        con.execute("INSERT INTO coverage_notes VALUES (?)", [withheld.group(0)])
    restored = [m for m in rows["matches"] if m["source"] != "cricsheet"]
    last = max(m["date"] for m in restored)
    con.execute("INSERT INTO coverage_notes VALUES (?)", [
        f"{len(restored)} withheld Afghanistan men's T20Is restored from archived Cricsheet snapshots "
        f"(Wayback Machine, 2024-10-09); Afghanistan men's T20Is after {last} are not in the database."])

    # Convenience views used by the stats layer.
    con.execute("""
        CREATE VIEW batting_innings AS
        SELECT d.match_id, d.innings, d.batter_id AS player_id, d.batting_team AS team,
               SUM(d.runs_batter) AS runs, SUM(d.is_ball_faced::INT) AS balls,
               SUM(d.is_four::INT) AS fours, SUM(d.is_six::INT) AS sixes
        FROM deliveries d WHERE NOT d.is_super_over
        GROUP BY ALL
    """)
    con.execute("""
        CREATE VIEW bowling_innings AS
        SELECT d.match_id, d.innings, d.bowler_id AS player_id, d.bowling_team AS team,
               SUM(d.is_legal_ball::INT) AS legal_balls, SUM(d.runs_conceded) AS runs_conceded,
               (SELECT COUNT(*) FROM wickets w WHERE w.match_id = d.match_id AND w.innings = d.innings
                    AND w.bowler_id = d.bowler_id AND w.is_bowler_wkt) AS wickets,
               SUM(d.is_dot::INT) AS dots
        FROM deliveries d WHERE NOT d.is_super_over
        GROUP BY ALL
    """)
    con.execute("""
        CREATE VIEW player_index AS
        SELECT p.player_id, p.name, p.unique_name,
               NULLIF(regexp_replace(regexp_replace(p.profile_source, '^Wikipedia: ', ''), ' \\(.*\\)$', ''), '') AS full_name,
               p.country, m.gender, COUNT(DISTINCT r.match_id) AS matches,
               MIN(m.date) AS first_match, MAX(m.date) AS last_match,
               p.batting_hand, p.bowling_style, p.bowling_type, p.primary_role
        FROM players p
        JOIN match_roles r USING (player_id)
        JOIN matches m USING (match_id)
        GROUP BY ALL
    """)
    con.execute("""
        CREATE VIEW deliveries_ctx AS
        SELECT d.*, m.gender, m.date, m.venue_id,
               bat.batting_hand AS batter_hand,
               bwl.bowling_arm, bwl.bowling_kind, bwl.bowling_type
        FROM deliveries d
        JOIN matches m USING (match_id)
        LEFT JOIN players bat ON bat.player_id = d.batter_id
        LEFT JOIN players bwl ON bwl.player_id = d.bowler_id
    """)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    download(args.refresh)

    rows = {k: [] for k in ("matches", "innings", "deliveries", "wickets", "match_roles", "players")}
    venue_seen = collections.defaultdict(set)
    team_counts = collections.defaultdict(collections.Counter)
    files = [(p, "cricsheet") for p in sorted((RAW / "t20s").glob("*.json"))]
    seen = {p.stem for p, _ in files}
    for a in ARCHIVES:
        for p in sorted(a["dir"].glob("*.json")):
            if p.stem not in seen:
                files.append((p, a["source"]))
                seen.add(p.stem)
    # Afghanistan T20Is never published by Cricsheet, fetched by ingest/sportmonks.py (needs an API token).
    for p in sorted((RAW / "sportmonks").glob("*.json")):
        if p.stem not in seen:
            files.append((p, "sportmonks"))
            seen.add(p.stem)
    for n, (path, source) in enumerate(files, 1):
        parse_match(path, source, rows, venue_seen, team_counts)
        if n % 1000 == 0:
            print(f"parsed {n}/{len(files)}")

    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))
    build(con, rows, venue_seen, team_counts)

    profiles = ROOT / "data" / "player_profiles.csv"
    if profiles.exists():
        from load_profiles import apply_profiles
        apply_profiles(con, profiles)

    for t in ("matches", "deliveries", "wickets", "players", "venues", "match_roles"):
        print(f"{t:12} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>10,}")
    con.close()


if __name__ == "__main__":
    main()
