"""Wickets.ai HTTP API (FastAPI). The Next.js app proxies /api/* here.

    .venv/bin/uvicorn wickets.api:app --port 8000

Accounts are required to ask questions (brief: email login, limited free questions per day). Filter
queries and story prompts don't use the model, so they don't count against the allowance.
"""
import csv
import io
import os
import threading
import time
import uuid
from collections import OrderedDict
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import filters, stories
from .db import Database, QueryError
from .settings import load_dotenv
from .store import AuthError, Store, default_store

load_dotenv()
FREE_DAILY = int(os.environ.get("WICKETS_FREE_DAILY", "5"))
COOKIE = "wk_session"
ATTRIBUTION = "Data from Cricsheet (cricsheet.org), ODC-BY. Player profiles from Wikipedia, CC BY-SA."
MAX_THREADS = 500


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    thread_id: Optional[str] = None


class Credentials(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class SaveReq(BaseModel):
    title: str = Field(max_length=200)
    list_name: str = Field(default="Saved", max_length=80)


class ReportReq(BaseModel):
    comment: str = Field(min_length=3, max_length=2000)


class ReportStatus(BaseModel):
    status: str = Field(pattern="^(open|resolved|wontfix)$")


def create_app(db=None, store=None, engine_factory=None):
    db = db or Database()
    store = store or default_store()
    if os.environ.get("ADMIN_EMAIL") and os.environ.get("ADMIN_PASSWORD"):
        store.ensure_admin(os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"])

    def make_engine():
        from .engine import Engine
        return Engine(db=db)

    needs_key = engine_factory is None  # the real engine calls the Anthropic API
    engine_factory = engine_factory or make_engine
    state = {"engine": None}
    threads = OrderedDict()  # thread_id -> Conversation (in memory; follow-ups after a restart start fresh)
    lock = threading.Lock()
    latest = db.query("SELECT MAX(date) FROM matches").rows[0][0]

    app = FastAPI(title="Wickets.ai", version="0.3")

    def engine():
        if state["engine"] is None:
            state["engine"] = engine_factory()
        return state["engine"]

    def current_user(request: Request):
        token = request.cookies.get(COOKIE) or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        return store.user_for_token(token)

    def require_user(user=Depends(current_user)):
        if not user:
            raise HTTPException(401, "sign in to use Wickets.ai")
        return user

    def require_admin(user=Depends(require_user)):
        if not user["is_admin"]:
            raise HTTPException(403, "admins only")
        return user

    def allowance(user):
        if user["is_admin"] or user["plan"] != "free":
            return None
        return max(FREE_DAILY - store.questions_today(user["id"]), 0)

    def owned_answer(answer_id, user):
        a = store.answer(answer_id)
        if not a or (a["user_id"] != user["id"] and not user["is_admin"]):
            raise HTTPException(404, "answer not found")
        return a

    # auth --------------------------------------------------------------------------------------
    @app.post("/api/auth/signup")
    def signup(body: Credentials, response: Response):
        try:
            store.create_user(body.email, body.password)
            token, user = store.login(body.email, body.password)
        except AuthError as e:
            raise HTTPException(400, str(e)) from None
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=30 * 86400)
        return {"user": user, "questions_left": allowance(user)}

    @app.post("/api/auth/login")
    def login(body: Credentials, response: Response):
        try:
            token, user = store.login(body.email, body.password)
        except AuthError as e:
            raise HTTPException(401, str(e)) from None
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=30 * 86400)
        return {"user": user, "questions_left": allowance(user)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        store.logout(request.cookies.get(COOKIE, ""))
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(user=Depends(current_user)):
        if not user:
            return {"user": None}
        return {"user": user, "questions_left": allowance(user), "free_daily": FREE_DAILY}

    # asking ------------------------------------------------------------------------------------
    @app.post("/api/ask")
    def ask(body: Ask, user=Depends(require_user)):
        if needs_key and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise HTTPException(503, "Questions aren't switched on yet: add ANTHROPIC_API_KEY to .env.local and restart "
                                     "the API. Filters and story prompts work without it.")
        left = allowance(user)
        if left == 0:
            raise HTTPException(429, f"You've used today's {FREE_DAILY} free questions. Filters and story "
                                     "prompts stay free; more questions come with a subscription.")
        with lock:
            tid = body.thread_id if body.thread_id in threads else uuid.uuid4().hex[:12]
            conv = threads.get(tid) or engine().conversation()
            threads[tid] = conv
            threads.move_to_end(tid)
            while len(threads) > MAX_THREADS:
                threads.popitem(last=False)
        start = time.time()
        payload = conv.ask(body.question).to_dict()
        aid = store.save_answer(user["id"], tid, "ask", body.question, payload, round(time.time() - start, 1))
        return {"id": aid, "thread_id": tid, **_public(payload),
                "questions_left": None if left is None else left - 1}

    @app.post("/api/query")
    def query(body: dict, user=Depends(require_user)):
        try:
            payload = filters.run(db, body, latest_date=_date(latest))
        except (filters.FilterError, QueryError, ValueError, TypeError) as e:
            raise HTTPException(400, str(e)) from None
        aid = store.save_answer(user["id"], None, "filter", payload["question"], payload)
        return {"id": aid, **_public(payload)}

    @app.get("/api/answers/{answer_id}")
    def get_answer(answer_id: str, user=Depends(require_user)):
        a = owned_answer(answer_id, user)
        return {"id": a["id"], "thread_id": a["thread_id"], "created_at": a["created_at"], **_public(a["payload"])}

    @app.get("/api/history")
    def history(user=Depends(require_user)):
        return {"items": store.history(user["id"])}

    # save, share, export, report ---------------------------------------------------------------
    @app.post("/api/answers/{answer_id}/save")
    def save(answer_id: str, body: SaveReq, user=Depends(require_user)):
        owned_answer(answer_id, user)
        store.save(user["id"], answer_id, body.title, body.list_name)
        return {"ok": True}

    @app.delete("/api/answers/{answer_id}/save")
    def unsave(answer_id: str, user=Depends(require_user)):
        store.unsave(user["id"], answer_id)
        return {"ok": True}

    @app.get("/api/saved")
    def saved(user=Depends(require_user)):
        return {"items": store.saved(user["id"])}

    @app.post("/api/answers/{answer_id}/share")
    def share(answer_id: str, user=Depends(require_user)):
        owned_answer(answer_id, user)
        return {"token": store.share(answer_id, user["id"])}

    @app.get("/api/share/{token}")
    def shared(token: str):
        a = store.shared_answer(token)
        if not a:
            raise HTTPException(404, "link not found")
        return {"id": a["id"], "created_at": a["created_at"], **_public(a["payload"])}

    @app.get("/api/answers/{answer_id}/export.csv")
    def export_csv(answer_id: str, user=Depends(require_user)):
        a = owned_answer(answer_id, user)["payload"]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"# {a['question']}"])
        w.writerow([f"# {a['answer']}"])
        table = a.get("table") or {}
        if table:
            w.writerow(table["columns"])
            w.writerows(table["rows"])
        for note in a.get("assumptions", []) + a.get("coverage_notes", []):
            w.writerow([f"# {note}"])
        w.writerow([f"# {ATTRIBUTION}"])
        name = f"wickets-{answer_id}.csv"
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/answers/{answer_id}/report")
    def report(answer_id: str, body: ReportReq, user=Depends(require_user)):
        if not store.answer(answer_id):
            raise HTTPException(404, "answer not found")
        store.report(answer_id, user["id"], body.comment)
        return {"ok": True}

    # lookups, prompts, admin -------------------------------------------------------------------
    @app.get("/api/players")
    def players(q: str, gender: Optional[str] = None, user=Depends(require_user)):
        return engine_free_find_player(db, q, gender)

    @app.get("/api/meta")
    def meta(user=Depends(require_user)):
        teams = db.query("SELECT DISTINCT t FROM (SELECT team1 AS t FROM matches UNION SELECT team2 FROM matches) "
                         "ORDER BY t", max_rows=1000).rows
        venues = db.query("SELECT v.venue_id, v.name, v.city, COUNT(*) AS n FROM venues v JOIN matches m USING (venue_id) "
                          "GROUP BY ALL ORDER BY n DESC", max_rows=1000).rows
        return {"teams": [t[0] for t in teams], "venues": [{"id": v[0], "name": v[1], "city": v[2]} for v in venues],
                "phases": sorted(filters.PHASES), "bowling_kinds": sorted(filters.BOWLING_KINDS),
                "bowling_types": sorted(filters.BOWLING_TYPES), "group_by": list(filters.GROUPS),
                "latest_match": latest, "attribution": ATTRIBUTION}

    @app.get("/api/stories")
    def story_prompts(user=Depends(require_user)):
        return stories.all_prompts(db)

    @app.get("/api/admin")
    def admin(user=Depends(require_admin)):
        return store.admin_stats()

    @app.post("/api/admin/reports/{report_id}")
    def set_report(report_id: int, body: ReportStatus, user=Depends(require_admin)):
        store.set_report_status(report_id, body.status)
        return {"ok": True}

    @app.get("/api/health")
    def health():
        return {"ok": True, "latest_match": latest}

    return app


def engine_free_find_player(db, q, gender=None):
    """Player autocomplete for the filter builder (no model call)."""
    terms = [t for t in q.replace(".", " ").split() if t][:4]
    if not terms:
        return {"candidates": []}
    where = " AND ".join("(COALESCE(full_name,'') ILIKE ? OR name ILIKE ?)" for _ in terms)
    params = [p for t in terms for p in (f"%{t}%", f"%{t}%")]
    if gender in ("male", "female"):
        where += " AND gender = ?"
        params.append(gender)
    r = db.query(f"SELECT player_id, name, full_name, country, gender, matches, first_match, last_match "
                 f"FROM player_index WHERE {where} ORDER BY matches DESC LIMIT 10", params=params)
    return {"candidates": r.as_dicts()}


def _public(payload):
    """What the browser sees: the answer and its proof, not the model's tool trace."""
    keep = ("question", "can_answer", "answer", "display", "table", "sql", "evidence", "assumptions",
            "coverage_notes", "error", "filters")
    out = {k: payload.get(k) for k in keep}
    out["cost_usd"] = (payload.get("usage") or {}).get("usd", 0)
    out["attribution"] = ATTRIBUTION
    return out


def _date(s):
    import datetime
    return datetime.date.fromisoformat(s)


app = create_app() if os.environ.get("WICKETS_NO_APP") != "1" else None
