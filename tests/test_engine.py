"""Engine control flow, tested offline: a scripted client stands in for Claude."""
import itertools
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from wickets.db import Database, QueryError  # noqa: E402
from wickets.engine import Engine  # noqa: E402

_ids = itertools.count()


def tool(name, **inp):
    return NS(type="tool_use", id=f"toolu_{next(_ids)}", name=name, input=inp)


def turn(*blocks, stop="tool_use"):
    return NS(content=list(blocks), stop_reason=stop,
              usage=NS(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=0))


class ScriptedClient:
    """Plays back assistant turns and records every request the engine sent."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot: the engine appends later
        return self.turns.pop(0)


@pytest.fixture(scope="module")
def db():
    return Database()


def engine_with(db, turns):
    client = ScriptedClient(turns)
    return Engine(db=db, client=client), client


KOHLI = "(SELECT player_id FROM player_index WHERE full_name = 'Virat Kohli')"


def test_full_answer_with_proof(db):
    eng, client = engine_with(db, [
        turn(tool("find_player", query="Kohli", gender="male")),
        turn(tool("submit_answer", can_answer=True, answer="Virat Kohli scored 4,188 T20I runs.",
                  sql=f"SELECT SUM(runs) AS runs FROM batting_innings WHERE player_id = {KOHLI}",
                  evidence_sql=f"SELECT match_id, SUM(balls) AS balls FROM batting_innings WHERE player_id = {KOHLI} GROUP BY 1",
                  display="sentence", assumptions=[])),
    ])
    a = eng.conversation().ask("How many T20I runs has Kohli scored?")
    assert a.can_answer and a.table["rows"] == [[4188]]
    assert a.evidence["match_count"] == 117 and a.evidence["balls"] == 3056
    assert a.evidence["matches"][0]["url"].startswith("https://www.espncricinfo.com/matches/engine/match/")
    assert a.coverage_notes == []  # retired before any withheld match
    # the request carries the server-side refusal fallback and the cached system prompt
    req = client.requests[0]
    assert req["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in req["betas"]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    # find_player found him
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert "V Kohli" in tool_result["content"]


def test_write_attempt_is_rejected_and_reported_back(db):
    eng, client = engine_with(db, [
        turn(tool("run_sql", sql="DELETE FROM matches")),
        turn(tool("run_sql", sql="SELECT 1; DROP TABLE matches")),
        turn(tool("submit_answer", can_answer=False, answer="Not possible.", sql=None, evidence_sql=None,
                  display="sentence", assumptions=[])),
    ])
    a = eng.conversation().ask("Delete everything")
    assert not a.can_answer
    errors = [t["error"] for t in a.trace if not t["ok"]]
    assert "only SELECT" in errors[0] and "exactly one statement" in errors[1]
    assert db.query("SELECT COUNT(*) FROM matches").rows[0][0] > 5000


def test_empty_answer_is_sent_back_for_a_fix(db):
    eng, client = engine_with(db, [
        turn(tool("submit_answer", can_answer=True, answer="x", sql="SELECT * FROM matches WHERE 1 = 0",
                  evidence_sql="SELECT match_id FROM matches LIMIT 1", display="sentence", assumptions=[])),
        turn(tool("submit_answer", can_answer=False, answer="No such record.", sql=None, evidence_sql=None,
                  display="sentence", assumptions=[])),
    ])
    a = eng.conversation().ask("Something with no data")
    assert not a.can_answer
    sent_back = client.requests[1]["messages"][-1]["content"][0]
    assert sent_back["is_error"] and "no rows" in sent_back["content"]


def test_cannot_answer_mentions_afghanistan_gap(db):
    eng, _ = engine_with(db, [
        turn(tool("submit_answer", can_answer=False, answer="No ball-by-ball data for that series.",
                  sql=None, evidence_sql=None, display="sentence", assumptions=[])),
    ])
    a = eng.conversation().ask("How did Afghanistan bat against Zimbabwe in December 2024?")
    assert not a.can_answer and "Afghanistan" in a.coverage_notes[0]


def test_bumrah_answer_gets_scoped_coverage_note(db):
    bumrah = "(SELECT player_id FROM player_index WHERE full_name = 'Jasprit Bumrah')"
    eng, _ = engine_with(db, [
        turn(tool("submit_answer", can_answer=True, answer="Bumrah has 123 T20I wickets.",
                  sql=f"SELECT SUM(wickets) AS wickets FROM bowling_innings WHERE player_id = {bumrah}",
                  evidence_sql=f"SELECT DISTINCT match_id FROM match_roles WHERE player_id = {bumrah}",
                  display="sentence", assumptions=[])),
    ])
    a = eng.conversation().ask("How many T20I wickets does Bumrah have?")
    assert a.table["rows"] == [[123]]
    assert len(a.coverage_notes) == 1 and "3 India T20I(s) against Afghanistan" in a.coverage_notes[0]


def test_follow_up_keeps_context(db):
    eng, client = engine_with(db, [
        turn(tool("submit_answer", can_answer=True, answer="a", sql="SELECT 1 AS x",
                  evidence_sql="SELECT match_id FROM matches LIMIT 1", display="sentence", assumptions=[])),
        turn(tool("submit_answer", can_answer=True, answer="b", sql="SELECT 2 AS x",
                  evidence_sql="SELECT match_id FROM matches LIMIT 1", display="sentence", assumptions=[])),
    ])
    conv = eng.conversation()
    conv.ask("first question")
    conv.ask("now only away games")
    msgs = client.requests[1]["messages"]
    assert msgs[0]["content"] == "first question" and msgs[-1]["content"] == "now only away games"


def test_refusal_and_prose_handling(db):
    eng, client = engine_with(db, [turn(NS(type="text", text="..."), stop="refusal")])
    assert eng.conversation().ask("q").error == "refusal"
    eng, client = engine_with(db, [
        turn(NS(type="text", text="Kohli has 4188 runs."), stop="end_turn"),
        turn(tool("submit_answer", can_answer=False, answer="n/a", sql=None, evidence_sql=None,
                  display="sentence", assumptions=[])),
    ])
    eng.conversation().ask("q")
    assert client.requests[1]["messages"][-1]["content"] == "Please finish by calling submit_answer."


def test_guard_blocks_file_access(db):
    with pytest.raises(QueryError):
        db.query("SELECT * FROM read_csv('tests/official_figures.csv')")
    with pytest.raises(QueryError):
        db.query("ATTACH 'x.duckdb'")
