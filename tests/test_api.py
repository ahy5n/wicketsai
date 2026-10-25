"""HTTP API end to end with a stand-in engine (no model calls)."""
import os
import sys
from pathlib import Path

import pytest

os.environ["WICKETS_NO_APP"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402

from wickets import api  # noqa: E402
from wickets.db import Database  # noqa: E402
from wickets.engine import Answer  # noqa: E402
from wickets.store import Store  # noqa: E402


class FakeConversation:
    def __init__(self, log):
        self.log = log
        self.turns = []

    def ask(self, q):
        self.turns.append(q)
        self.log.append(list(self.turns))
        return Answer(q, True, "Virat Kohli scored 4,188 T20I runs.", table={"columns": ["runs"], "rows": [[4188]]},
                      sql="SELECT 4188 AS runs", evidence={"match_count": 117, "balls": 3056, "matches": []},
                      usage={"usd": 0.12})


class FakeEngine:
    def __init__(self):
        self.log = []

    def conversation(self):
        return FakeConversation(self.log)


@pytest.fixture()
def env(tmp_path):
    os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"] = "admin@wickets.test", "admin-pass-123"
    fake = FakeEngine()
    app = api.create_app(db=Database(), store=Store(tmp_path / "app.sqlite"), engine_factory=lambda: fake)
    yield TestClient(app), fake
    del os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"]


def signup(c, email="writer@paper.test"):
    r = c.post("/api/auth/signup", json={"email": email, "password": "correct horse"})
    assert r.status_code == 200, r.text
    return r.json()


def test_login_required_and_auth_flow(env):
    c, _ = env
    assert c.post("/api/ask", json={"question": "Kohli runs?"}).status_code == 401
    assert c.get("/api/me").json() == {"user": None}
    assert c.post("/api/auth/signup", json={"email": "bad", "password": "correct horse"}).status_code == 400
    assert c.post("/api/auth/signup", json={"email": "w@p.test", "password": "short"}).status_code == 400
    me = signup(c)
    assert me["questions_left"] == 5
    assert c.post("/api/auth/signup", json={"email": "writer@paper.test", "password": "x" * 9}).status_code == 400
    c.post("/api/auth/logout")
    assert c.get("/api/me").json() == {"user": None}
    assert c.post("/api/auth/login", json={"email": "writer@paper.test", "password": "wrong pass"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "Writer@Paper.test", "password": "correct horse"}).status_code == 200


def test_ask_follow_up_and_daily_limit(env):
    c, fake = env
    signup(c)
    a = c.post("/api/ask", json={"question": "How many runs has Kohli scored?"}).json()
    assert a["table"]["rows"] == [[4188]] and a["questions_left"] == 4 and "Cricsheet" in a["attribution"]
    assert "trace" not in a  # the model's tool trace stays server-side
    b = c.post("/api/ask", json={"question": "And in 2016?", "thread_id": a["thread_id"]}).json()
    assert b["thread_id"] == a["thread_id"] and fake.log[-1] == ["How many runs has Kohli scored?", "And in 2016?"]
    for _ in range(3):
        assert c.post("/api/ask", json={"question": "again?"}).status_code == 200
    r = c.post("/api/ask", json={"question": "one too many"})
    assert r.status_code == 429 and "free questions" in r.json()["detail"]
    # filters don't use the model and stay free
    q = c.post("/api/query", json={"perspective": "batting", "player_id": "ba607b88"})
    assert q.status_code == 200 and q.json()["table"]["rows"][0][1] == 4188


def test_answers_are_private_but_share_links_are_public(env):
    c, _ = env
    signup(c, "a@paper.test")
    aid = c.post("/api/ask", json={"question": "Kohli runs?"}).json()["id"]
    token = c.post(f"/api/answers/{aid}/share").json()["token"]
    assert c.post(f"/api/answers/{aid}/share").json()["token"] == token  # stable link
    c.post("/api/auth/logout")
    signup(c, "b@paper.test")
    assert c.get(f"/api/answers/{aid}").status_code == 404
    assert c.post(f"/api/answers/{aid}/save", json={"title": "x"}).status_code == 404
    c.post("/api/auth/logout")
    shared = c.get(f"/api/share/{token}")
    assert shared.status_code == 200 and shared.json()["answer"].startswith("Virat Kohli")
    assert c.get("/api/share/nope").status_code == 404


def test_save_export_and_report(env):
    c, _ = env
    signup(c)
    aid = c.post("/api/query", json={"perspective": "bowling", "player_id": "462411b3", "phases": ["death"]}).json()["id"]
    assert c.post(f"/api/answers/{aid}/save", json={"title": "Bumrah at the death", "list_name": "WC preview"}).status_code == 200
    items = c.get("/api/saved").json()["items"]
    assert items[0]["title"] == "Bumrah at the death" and items[0]["list_name"] == "WC preview"
    csv_text = c.get(f"/api/answers/{aid}/export.csv").text
    assert "economy" in csv_text and "Data from Cricsheet" in csv_text and "Afghanistan" in csv_text
    assert c.post(f"/api/answers/{aid}/report", json={"comment": "Economy looks off"}).status_code == 200
    assert c.get("/api/admin").status_code == 403
    c.delete(f"/api/answers/{aid}/save")
    assert c.get("/api/saved").json()["items"] == []


def test_admin_dashboard(env):
    c, _ = env
    signup(c)
    aid = c.post("/api/ask", json={"question": "Kohli runs?"}).json()["id"]
    c.post(f"/api/answers/{aid}/report", json={"comment": "wrong total"})
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"email": "admin@wickets.test", "password": "admin-pass-123"}).status_code == 200
    me = c.get("/api/me").json()
    assert me["user"]["is_admin"] == 1 and me["questions_left"] is None  # unlimited
    d = c.get("/api/admin").json()
    assert d["totals"]["questions"] == 1 and d["totals"]["usd"] == 0.12
    assert d["reports"][0]["comment"] == "wrong total" and d["reports"][0]["status"] == "open"
    assert c.post(f"/api/admin/reports/{d['reports'][0]['id']}", json={"status": "resolved"}).status_code == 200
    assert c.get("/api/admin").json()["reports"][0]["status"] == "resolved"
    assert any(u["email"] == "writer@paper.test" for u in d["users"])


def test_filter_validation_and_lookups(env):
    c, _ = env
    signup(c)
    assert c.post("/api/query", json={"perspective": "batting", "player_id": "x'; DROP TABLE matches; --"}).status_code == 400
    assert c.post("/api/query", json={"perspective": "fielding"}).status_code == 400
    assert c.post("/api/query", json={"perspective": "batting", "phases": ["middle", "slog"]}).status_code == 400
    cands = c.get("/api/players", params={"q": "smriti"}).json()["candidates"]
    assert cands[0]["full_name"] == "Smriti Mandhana"
    meta = c.get("/api/meta").json()
    assert "India" in meta["teams"] and "wrist-spin" in meta["bowling_types"] and meta["venues"]
    s = c.get("/api/stories").json()
    assert set(s) == {"stat_of_the_day", "milestones", "streaks"} and s["streaks"]
