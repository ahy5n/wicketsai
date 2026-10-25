"""Build data/player_profiles.csv (batting hand, bowling style, role, height) from Wikipedia.

Route: Cricsheet register -> ESPNcricinfo id -> Wikidata (P2697) -> English Wikipedia article
-> {{Infobox cricketer}} fields. Wikipedia text is CC BY-SA 4.0; credit "Wikipedia" alongside Cricsheet.

Usage:
    python ingest/fetch_profiles.py     # needs data/wickets.duckdb from ingest.py
    python ingest/ingest.py             # re-run to apply the profiles
"""
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "player_profiles.csv"
CACHE = ROOT / "data" / "raw" / "wiki_infobox_cache.json"
UA = "WicketsAI-demo/0.1 (cricket stats research prototype)"
SPARQL = ("SELECT ?ci ?article WHERE { ?item wdt:P2697 ?ci . ?article schema:about ?item ; "
          "schema:isPartOf <https://en.wikipedia.org/> . }")


def get(url, params):
    # POST keeps long title lists under URL-length limits; both endpoints accept it.
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
    err = None
    for attempt in range(7):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            err = e
            retry_after = getattr(e, "headers", {}) and e.headers.get("Retry-After")
            time.sleep(int(retry_after) if retry_after and retry_after.isdigit() else 5 * 2 ** attempt)
    raise RuntimeError(f"failed: {url}: {err!r}")


def cricinfo_to_title():
    data = get("https://query.wikidata.org/sparql", {"query": SPARQL, "format": "json"})
    out = {}
    for b in data["results"]["bindings"]:
        ci = b["ci"]["value"]
        if ci.isdigit():
            out[int(ci)] = urllib.parse.unquote(b["article"]["value"].rsplit("/wiki/", 1)[1]).replace("_", " ")
    return out


def fetch_wikitext(titles, cache):
    todo = [t for t in titles if t not in cache]
    for i in range(0, len(todo), 20):
        batch = todo[i:i + 20]
        data = get("https://en.wikipedia.org/w/api.php", {
            "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
            "redirects": 1, "format": "json", "formatversion": 2, "titles": "|".join(batch),
        })
        q = data["query"]
        alias = {r["from"]: r["to"] for r in q.get("normalized", []) + q.get("redirects", [])}
        pages = {p["title"]: p for p in q["pages"]}
        for t in batch:
            target = alias.get(alias.get(t, t), alias.get(t, t))
            page = pages.get(target, {})
            revs = page.get("revisions")
            text = revs[0]["slots"]["main"]["content"] if revs else ""
            cache[t] = infobox_fields(text)
        print(f"wikipedia {min(i + 20, len(todo))}/{len(todo)}", flush=True)
        CACHE.write_text(json.dumps(cache))
        time.sleep(1.5)
    return cache


def clean(v):
    v = re.sub(r"<ref[^>]*/>|<ref.*?</ref>|<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", v)  # [[target|label]] -> label
    v = re.sub(r"<br\s*/?>", ", ", v)
    v = re.sub(r"'{2,}", "", v)
    v = re.sub(r"\{\{(?:nowrap|small)\|([^{}]*)\}\}", r"\1", v, flags=re.I)
    v = re.sub(r"\{\{[^{}]*\}\}", "", v)  # footnotes ({{efn|...}}) and other templates
    v = re.sub(r"\s+", " ", v).strip(" ,")
    # An empty field followed by the next one ('| role = ...') is empty, not that value.
    return "" if v.startswith("|") or v.startswith("}}") else v


def infobox_fields(text):
    m = re.search(r"\{\{\s*Infobox cricketer", text, re.I)
    if not m:
        return {}
    fields = {}
    for key in ("batting", "bowling", "role", "height"):
        f = re.search(r"\n\s*\|\s*" + key + r"[ \t]*=[ \t]*(.*)", text[m.start():m.start() + 20000])
        if f:
            fields[key] = f.group(1)
    if "height" in fields:
        fields["height"] = parse_height(fields["height"])
    return {k: (clean(v) if isinstance(v, str) else v) for k, v in fields.items()}


def parse_height(v):
    m = re.search(r"m\s*=\s*([\d.]+)", v) or re.search(r"\b(1\.\d{1,2})\s*m\b", v)
    if m:
        return round(float(m.group(1)) * 100)
    m = re.search(r"cm\s*=\s*(\d+)", v) or re.search(r"\b(1\d\d)\s*cm\b", v)
    if m:
        return int(m.group(1))
    m = re.search(r"ft\s*=\s*(\d)\s*\|\s*in\s*=\s*([\d.]+)", v)
    if m:
        return round((int(m.group(1)) * 12 + float(m.group(2))) * 2.54)
    return None


def batting_hand(v):
    v = (v or "").lower()
    if v.startswith("left"):
        return "left"
    if v.startswith("right"):
        return "right"
    return None


def classify_bowling(v):
    """Map free-text style to (arm, kind, type). Uses the first style listed."""
    s = (v or "").lower()
    if not s or s in ("none", "-", "n/a"):
        return None, None, None
    s = re.split(r",|/|;| and ", s)[0]
    arm = "left" if "left" in s else "right" if "right" in s else None
    if "orthodox" in s and "unorthodox" not in s:
        return "left", "spin", "orthodox"
    if "unorthodox" in s or "chinaman" in s or ("wrist" in s and arm == "left"):
        return "left", "spin", "wrist-spin"
    if "leg" in s and ("break" in s or "spin" in s) or "googly" in s:
        return arm or "right", "spin", "leg-spin"
    if "off" in s and ("break" in s or "spin" in s):
        return arm or "right", "spin", "off-spin"
    for t in ("fast-medium", "medium-fast", "fast", "medium"):
        if t in s.replace(" ", "-") or t in s:
            return arm, "pace", t
    if "slow" in s and arm == "left":
        return "left", "spin", "orthodox"
    if "seam" in s:
        return arm, "pace", "medium"
    if "slow" in s or "spin" in s:
        return arm, "spin", None  # spinner, variety not stated
    return arm, None, None


def main():
    con = duckdb.connect(str(ROOT / "data" / "wickets.duckdb"), read_only=True)
    players = con.execute("SELECT player_id, cricinfo_id FROM players WHERE cricinfo_id IS NOT NULL").fetchall()
    con.close()

    titles = cricinfo_to_title()
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    wanted = sorted({titles[ci] for _, ci in players if ci in titles})
    cache = fetch_wikitext(wanted, cache)

    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["player_id", "batting_hand", "bowling_style", "bowling_arm", "bowling_kind",
                    "bowling_type", "primary_role", "height_cm", "profile_source"])
        for pid, ci in players:
            t = titles.get(ci)
            fields = cache.get(t) if t else None
            if not fields:
                continue
            fields = {k: clean(v) if isinstance(v, str) else v for k, v in fields.items()}
            arm, kind, btype = classify_bowling(fields.get("bowling"))
            w.writerow([pid, batting_hand(fields.get("batting")), fields.get("bowling") or None, arm, kind, btype,
                        fields.get("role") or None, fields.get("height"),
                        "Wikipedia: " + t])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
