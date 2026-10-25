"""The grader itself: answering every question with its own gold query must score 100%, and plausible
wrong answers must fail. Runs offline."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from run_eval import Grader  # noqa: E402
from wickets.db import Database  # noqa: E402

QS = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())


@pytest.fixture(scope="module")
def grader():
    return Grader(Database())


def oracle(grader, q):
    if q["grade"] == "refuse":
        return {"can_answer": False, "answer": "Not in this database.", "table": None, "coverage_notes": [], "assumptions": []}
    r = grader.db.query(q["gold_sql"], max_rows=50)
    return {"can_answer": True, "answer": "see table", "table": {"columns": r.columns, "rows": r.rows},
            "coverage_notes": [], "assumptions": []}


def test_suite_size():
    assert len(QS) >= 100


@pytest.mark.parametrize("q", QS, ids=[q["id"] for q in QS])
def test_gold_answer_passes(grader, q):
    ok, detail = grader.grade(q, oracle(grader, q))
    assert ok, detail


def test_wrong_answers_fail(grader):
    q = next(q for q in QS if q["id"] == "career_runs_kohli")
    assert not grader.grade(q, {"can_answer": True, "answer": "Kohli has 4,135 runs.", "table": {"rows": [[4135]]}})[0]
    assert grader.grade(q, {"can_answer": True, "answer": "Kohli has 4,188 runs.", "table": None})[0]  # sentence counts
    q = next(q for q in QS if q["id"] == "career_sr_kohli")
    assert grader.grade(q, {"can_answer": True, "answer": "", "table": {"rows": [[137.0]]}})[0]  # 1-dp rounding ok
    assert not grader.grade(q, {"can_answer": True, "answer": "", "table": {"rows": [[136.9]]}})[0]
    q = next(q for q in QS if q["id"] == "refuse_ipl")
    assert not grader.grade(q, {"can_answer": True, "answer": "Gayle", "table": {"rows": [["CH Gayle"]]}})[0]
    q = next(q for q in QS if q["id"] == "rec_most_runs_men")
    full_names = {"can_answer": True, "answer": "", "table": {"rows": [
        ["Babar Azam"], ["Jos Buttler"], ["Rohit Sharma"], ["Virat Kohli"], ["Paul Stirling"]]}}
    assert grader.grade(q, full_names)[0]  # full names are accepted for scorecard names
    full_names["table"]["rows"].pop()
    assert not grader.grade(q, full_names)[0]


def test_disclosure_check(grader):
    q = next(q for q in QS if q["id"] == "career_wkts_bumrah")
    assert grader.disclosed(q, {"answer": "", "assumptions": [], "coverage_notes": ["3 India T20I(s) against Afghanistan ..."]})
    assert not grader.disclosed(q, {"answer": "", "assumptions": [], "coverage_notes": []})
