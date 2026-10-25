"""Every example in the model's query library runs and returns rows."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from wickets.db import Database  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "wickets" / "examples.yaml").read_text())


@pytest.fixture(scope="module")
def db():
    return Database()


@pytest.mark.parametrize("ex", EXAMPLES, ids=[e["question"][:50] for e in EXAMPLES])
def test_example_runs(db, ex):
    r = db.query(ex["sql"])
    assert r.row_count > 0 and all(v is not None for v in r.rows[0][:2])
