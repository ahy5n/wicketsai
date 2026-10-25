# Wickets.ai: T20I demo

Ball-by-ball men's and women's T20Is in DuckDB (`data/wickets.duckdb`).

```bash
python3 -m venv .venv && .venv/bin/pip install duckdb pytest
.venv/bin/python ingest/ingest.py          # download + build the database
.venv/bin/python ingest/fetch_profiles.py  # batting hand / bowling style from Wikipedia
.venv/bin/python ingest/ingest.py          # rebuild with profiles applied
.venv/bin/python -m pytest tests -v        # checks against official figures
```

## Sources and attribution

| Data | Source | Licence |
|---|---|---|
| Ball-by-ball T20Is | Cricsheet `t20s_json.zip` | ODC-BY: show "Data from Cricsheet" |
| Afghanistan men's T20Is, 2010 to Jun 2024 (133 matches) | Cricsheet `t20s_male.zip` (legacy YAML) as archived by the Wayback Machine on 2024-10-09, converted by `ingest/legacy_yaml.py` | ODC-BY |
| Afghanistan men's T20Is after Jun 2024 (30 matches, list in `data/afghanistan_t20is_missing.csv`) | Sportmonks Cricket API via `ingest/sportmonks.py`, **not yet fetched: needs a paid token** in `.env` as `SPORTMONKS_API_TOKEN` | Sportmonks licence |
| Player register / Cricinfo IDs | Cricsheet `people.csv` | ODC-BY |
| Batting hand, bowling style, role, height | English Wikipedia `{{Infobox cricketer}}`, linked via Wikidata P2697 | CC BY-SA 4.0: credit Wikipedia |

## Known coverage gaps (also stored in the `coverage_notes` table)

- Afghanistan men's T20Is after 2024-06-26 (30 matches): played after Cricsheet began withholding (Dec 2024), so never published. The Sportmonks importer is built and validated on their documented sample, but hasn't been run (no token). Sportmonks' sample match differs from Cricsheet by 1 run on one ball, so imported matches are tagged `source='sportmonks'`.
- Women's T20Is: about 225 of the numbered matches from 2004-2016 have no ball-by-ball record in Cricsheet (including all of #1-39). Cricsheet's /missing page doesn't list T20Is.
- Associate men's T20Is (numbered since 2019) are only partly covered.
- Cricsheet numbering errors: men's match numbered 4931 (real maximum about 4201); five T20I numbers used twice.
- Matches abandoned without a ball bowled aren't in Cricsheet, though Cricinfo counts them as matches played, so match counts can run one or two short (e.g. Bumrah, IND v SL, Guwahati, 2020-01-05).
- Captain and wicketkeeper flags aren't in Cricsheet (NULL).
- Player profiles exist only for players with an English Wikipedia article linked to their Cricinfo ID.

## Conventions

- `over` is 0-indexed. `phase` is powerplay = overs 1-6, middle = 7-15, death = 16-20 (ICC).
- `runs_conceded` excludes byes, leg-byes and penalty runs. Wides and no-balls are charged to the bowler.
- `is_ball_faced` excludes wides. `is_bowler_wkt` excludes run outs, retirements and obstructing the field.
- Super-over balls are flagged `is_super_over` and excluded from the career views.

## Stage 2: asking questions

```bash
echo 'ANTHROPIC_API_KEY=...' >> .env                     # git-ignored
.venv/bin/python -m wickets "How many sixes has Suryakumar Yadav hit off spinners?"
.venv/bin/python -m wickets                               # interactive; follow-ups keep context
.venv/bin/python eval/run_eval.py --limit 20 --max-usd 5  # accuracy suite sample (real API spend)
```

How a question becomes an answer (`wickets/engine.py`):
1. Claude (`claude-opus-5-5`, effort `medium`, server-side refusal fallback on) gets the schema
   (`docs/schema.md`), the conventions (`docs/conventions.md`) and 18 tested example queries
   (`wickets/examples.yaml`), all in one cached system prompt.
2. It resolves names with `find_player`, explores with `run_sql`, then calls `submit_answer` with a
   sentence, the answer SQL and an evidence SQL listing the matches used.
3. The engine re-runs both queries itself. The answer table is the database's output, never the
   model's. Empty or failing queries go back to the model to fix, and "can't answer" is a first-class
   result.
4. The proof panel (`wickets/proof.py`) lists the matches with ESPNcricinfo links and the balls used.
   It also attaches coverage notes computed from those matches, e.g. "3 India T20I(s) against
   Afghanistan (Sep 2026) are not in the database".

Safety: SQL runs on a read-only connection with external file access disabled. Only a single SELECT is
accepted, with a 15 s timeout and a row cap.

Accuracy suite (`eval/questions.yaml`, built by `eval/build_questions.py`): 176 questions, each with a
hand-written gold query. Five golds are pinned to official ESPNcricinfo figures. The set covers player
careers, phases, bowling-type splits, head-to-heads, records, teams, venues, trends, the six brief
examples, 12 questions that must be refused, 3 coverage traps and 5 two-turn follow-ups.
`tests/test_eval_grader.py` checks the grader: every gold answer passes, and near-misses
(4,135 for 4,188; 136.9 for 137.04) fail.

## Stage 3: the web app

Two processes: the Python API and the Next.js app (`web/`), which proxies `/api` to it.

```bash
.venv/bin/uvicorn wickets.api:app --port 8000
```

```bash
cd web && PATH=$HOME/.local/node/bin:$PATH npm run dev    # http://localhost:3000
```

`.env` (git-ignored) holds `ANTHROPIC_API_KEY`, needed for questions; filters and story prompts work
without it. It also holds `ADMIN_EMAIL` / `ADMIN_PASSWORD` for the local admin account, created when
the API starts. Free accounts get `WICKETS_FREE_DAILY` questions a day (default 5).

Pages: Ask (`/`, with follow-ups and story prompts), Filters (`/filters`), Saved and recent (`/saved`),
a saved answer (`/a/<id>`), a public share link (`/s/<token>`) and Admin (`/admin`).

Each answer card has the copy-ready sentence, a chart where one fits, a stats table, assumptions,
coverage warnings and the proof panel (query, matches with ESPNcricinfo links, ball count). Actions:
Save to a named list, Share link, CSV, PNG and Report an issue.

Notes:
- Accounts are local (PBKDF2 password hashes in `data/app.sqlite`), with `wickets/store.py` as the
  swap point for Supabase Auth.
- Node.js lives in `~/.local/node` (v22 LTS, not on the shell PATH by default).
- The accent colour is a placeholder for The Follow Through's teal: `--accent` in `web/app/globals.css`.
- Follow-up threads are held in memory and start fresh after an API restart.
