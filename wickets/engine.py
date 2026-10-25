"""Question in, verified answer out.

Claude writes read-only SQL against a documented schema, using tools to explore and test queries,
then submits a final answer. The engine re-runs the submitted SQL itself (the table shown is the
database's output, never the model's), builds the proof panel and attaches coverage notes.
"""
import datetime
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import anthropic
import yaml

from . import proof
from .db import ROOT, Database, QueryError
from .settings import load_dotenv

load_dotenv()

MODEL = os.environ.get("WICKETS_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("WICKETS_EFFORT", "medium")
MAX_TURNS = 14
# USD per million tokens for MODEL (claude-opus-5-5); cache writes bill at 1.25x input, reads at 0.05x.
PRICE = {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20}

SYSTEM_INTRO = """You are the query engine behind Wickets.ai, a research tool for cricket journalists.
You answer questions about men's and women's T20 Internationals from a ball-by-ball database.

How you work:
- Never answer from memory. Every number must come from a query you ran on the database.
- Resolve names with find_player before using them (several players can share a name: pick by
  country, gender and era, and say which you chose if the question was ambiguous).
- Explore and test with run_sql. Check that results look sensible (e.g. a career total of 0, or an
  economy of 40, means the query is wrong).
- Follow the conventions document exactly (ICC conventions, phases, what counts as a ball faced, a
  bowler's wicket, etc.). State any assumption a reader might not share.
- Finish by calling submit_answer exactly once. Its `sql` is re-run by the system and the result is
  shown to the reader as the answer table, so it must return the answer itself (a few rows, readable
  column names, rounded rates). `evidence_sql` must return a `match_id` column listing the matches the
  answer is drawn from (all of them, one row each), optionally with a `balls` column counting the
  deliveries used per match.
- If the database can't answer reliably (other formats, data that isn't recorded such as ball speed,
  line and length or field positions, future events, opinions, or results that look wrong and you
  can't fix), submit with can_answer = false and explain briefly. Never guess.
- Write `answer` as one or two sentences a journalist can paste into copy: the key number(s) first,
  then context. No hedging beyond the stated assumptions. Coverage gaps are added automatically;
  don't repeat them.
"""


@dataclass
class Answer:
    question: str
    can_answer: bool
    answer: str
    display: str = "sentence"
    table: dict = None
    sql: str = None
    evidence: dict = None
    assumptions: list = field(default_factory=list)
    coverage_notes: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    error: str = None

    def to_dict(self):
        return asdict(self)


def _system_prompt():
    docs = ROOT / "docs"
    examples = yaml.safe_load((ROOT / "wickets" / "examples.yaml").read_text())
    ex = "\n\n".join(
        f"Q: {e['question']}\n" + (f"Note: {e['notes']}\n" if e.get("notes") else "") + f"```sql\n{e['sql'].strip()}\n```"
        for e in examples)
    return (f"{SYSTEM_INTRO}\n\n# Conventions\n\n{(docs / 'conventions.md').read_text()}\n\n"
            f"# Schema\n\n{(docs / 'schema.md').read_text()}\n\n# Tested example queries\n\n{ex}")


TOOLS = [
    {
        "name": "find_player",
        "description": "Search players by any part of their name (full name, scorecard name like 'JJ Bumrah', or "
                       "surname). Returns up to 15 candidates with player_id, names, country, gender, match count "
                       "and career span. Use the player_id in SQL.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name or part of a name"},
                "gender": {"type": ["string", "null"], "enum": ["male", "female", None]},
            },
            "required": ["query", "gender"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_sql",
        "description": "Run one read-only DuckDB SELECT and see up to 50 rows. Use it to explore, test and check "
                       "queries before submitting.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_answer",
        "description": "Submit the final answer. Call exactly once, at the end.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "can_answer": {"type": "boolean"},
                "answer": {"type": "string", "description": "Copy-ready sentence(s), or why it can't be answered"},
                "sql": {"type": ["string", "null"], "description": "Query whose result is the answer table"},
                "evidence_sql": {"type": ["string", "null"],
                                 "description": "Query returning match_id (and optionally balls) for every match used"},
                "display": {"type": "string", "enum": ["sentence", "table", "bar", "line"]},
                "assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["can_answer", "answer", "sql", "evidence_sql", "display", "assumptions"],
            "additionalProperties": False,
        },
    },
]


class Engine:
    def __init__(self, db=None, client=None, model=MODEL, effort=EFFORT):
        self.db = db or Database()
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.system = [{"type": "text", "text": _system_prompt(), "cache_control": {"type": "ephemeral"}}]
        self.latest_date = datetime.date.fromisoformat(self.db.query("SELECT MAX(date) FROM matches").rows[0][0])

    def conversation(self):
        return Conversation(self)

    # tools ------------------------------------------------------------------------------------
    def find_player(self, query, gender=None):
        terms = [t for t in query.replace(".", " ").split() if t]
        if not terms:
            return {"error": "empty query"}
        where = " AND ".join(
            "(COALESCE(full_name,'') ILIKE ? OR name ILIKE ? OR unique_name ILIKE ?)" for _ in terms)
        params = [p for t in terms for p in (f"%{t}%",) * 3]
        if gender:
            where += " AND gender = ?"
            params.append(gender)
        cur = self.db.con.execute(f"""
            SELECT player_id, name, full_name, country, gender, matches, first_match, last_match,
                   batting_hand, bowling_type
            FROM player_index WHERE {where} ORDER BY matches DESC LIMIT 15""", params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, [str(v) if isinstance(v, datetime.date) else v for v in r])) for r in cur.fetchall()]
        return {"candidates": rows} if rows else {"candidates": [], "note": "no player matches; try the surname"}

    def run_sql(self, sql):
        r = self.db.query(sql, max_rows=50)
        return {"columns": r.columns, "rows": r.rows, "row_count": r.row_count,
                "truncated": r.truncated, "elapsed_s": r.elapsed_s}

    def finalise(self, question, args):
        """Validate a submit_answer call and build the Answer, or raise QueryError for the model to fix."""
        if not args["can_answer"]:
            return Answer(question, False, args["answer"], assumptions=args["assumptions"],
                          coverage_notes=proof.coverage_notes([], "", question, self.latest_date))
        if not args["sql"] or not args["evidence_sql"]:
            raise QueryError("can_answer is true, so sql and evidence_sql are both required")
        table = self.db.query(args["sql"], max_rows=200)
        if table.row_count == 0:
            raise QueryError("the answer sql returned no rows; fix it, or submit can_answer=false")
        ev_res = self.db.query(args["evidence_sql"], max_rows=100_000)
        if "match_id" not in ev_res.columns:
            raise QueryError("evidence_sql must return a column named match_id")
        mi = ev_res.columns.index("match_id")
        match_ids = sorted({r[mi] for r in ev_res.rows if r[mi] is not None})
        balls = None
        if "balls" in ev_res.columns:
            bi = ev_res.columns.index("balls")
            balls = int(sum(r[bi] or 0 for r in ev_res.rows))
        evidence, match_rows = proof.build_evidence(self.db, match_ids, balls)
        return Answer(
            question, True, args["answer"], display=args["display"],
            table={"columns": table.columns, "rows": table.rows, "truncated": table.truncated},
            sql=self.db.check(args["sql"]), evidence=asdict(evidence), assumptions=args["assumptions"],
            coverage_notes=proof.coverage_notes(match_rows, args["sql"], question, self.latest_date))


class Conversation:
    """One journalist's thread: follow-ups ('now only away games') keep the earlier context."""

    def __init__(self, engine):
        self.engine = engine
        self.messages = []

    def ask(self, question):
        e = self.engine
        self.messages.append({"role": "user", "content": question})
        trace, usage = [], {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
        for _ in range(MAX_TURNS):
            try:
                response = e.client.beta.messages.create(
                    model=e.model,
                    max_tokens=16000,
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    thinking={"type": "adaptive"},
                    output_config={"effort": e.effort},
                    system=e.system,
                    tools=TOOLS,
                    messages=self.messages,
                )
            except anthropic.APIError as err:
                return Answer(question, False, "The query engine is unavailable right now.",
                              error=f"{type(err).__name__}: {err}", trace=trace, usage=_cost(usage))
            _add_usage(usage, response.usage)
            # Append the full content (thinking blocks included) unchanged: history is append-only.
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                return Answer(question, False, "This question can't be answered here.", trace=trace,
                              usage=_cost(usage), error="refusal")
            if response.stop_reason == "max_tokens":
                return Answer(question, False, "The answer ran too long to complete.", trace=trace,
                              usage=_cost(usage), error="max_tokens")

            calls = [b for b in response.content if b.type == "tool_use"]
            if not calls:
                # The model replied in prose without submitting; ask it to finish properly.
                self.messages.append({"role": "user", "content": "Please finish by calling submit_answer."})
                continue

            results, final = [], None
            for call in calls:
                try:
                    if call.name == "find_player":
                        out = e.find_player(call.input["query"], call.input.get("gender"))
                    elif call.name == "run_sql":
                        out = e.run_sql(call.input["sql"])
                    elif call.name == "submit_answer":
                        final = e.finalise(question, call.input)
                        out = {"status": "accepted"}
                    else:
                        raise QueryError(f"unknown tool {call.name}")
                    trace.append({"tool": call.name, "input": call.input, "ok": True})
                    results.append({"type": "tool_result", "tool_use_id": call.id,
                                    "content": json.dumps(out, default=str)})
                except QueryError as err:
                    trace.append({"tool": call.name, "input": call.input, "ok": False, "error": str(err)})
                    results.append({"type": "tool_result", "tool_use_id": call.id,
                                    "content": f"Error: {err}", "is_error": True})
            self.messages.append({"role": "user", "content": results})
            if final:
                final.trace, final.usage = trace, _cost(usage)
                return final
        return Answer(question, False, "Couldn't reach a reliable answer.", trace=trace, usage=_cost(usage),
                      error="max_turns")


def _add_usage(total, u):
    total["input"] += u.input_tokens or 0
    total["output"] += u.output_tokens or 0
    total["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
    total["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0


def _cost(usage):
    usd = sum(usage[k] * PRICE[k] for k in PRICE) / 1e6
    return {**usage, "usd": round(usd, 4)}
