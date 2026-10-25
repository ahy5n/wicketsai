"""App state: users, sessions, the question log, saved queries, share links and issue reports.

SQLite, separate from the read-only cricket database. Accounts are local for the demo (email +
password, scrypt-hashed); `Store` is the seam where Supabase Auth would plug in later.
"""
import datetime
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading

from .db import ROOT

APP_DB = ROOT / "data" / "app.sqlite"
SESSION_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, pw_salt TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0, plan TEXT NOT NULL DEFAULT 'free', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS answers (
    id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), thread_id TEXT, kind TEXT NOT NULL,
    question TEXT NOT NULL, payload TEXT NOT NULL, can_answer INTEGER NOT NULL, usd REAL NOT NULL DEFAULT 0,
    seconds REAL, error TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS saved (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), answer_id TEXT NOT NULL REFERENCES answers(id),
    title TEXT NOT NULL, list_name TEXT NOT NULL DEFAULT 'Saved', created_at TEXT NOT NULL,
    UNIQUE (user_id, answer_id));
CREATE TABLE IF NOT EXISTS shares (
    token TEXT PRIMARY KEY, answer_id TEXT NOT NULL REFERENCES answers(id), created_by INTEGER, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY, answer_id TEXT NOT NULL REFERENCES answers(id), user_id INTEGER, comment TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS answers_user_day ON answers (user_id, created_at);
"""


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _hash(password, salt):
    # PBKDF2-SHA256 at OWASP's recommended iteration count (this Python's hashlib has no scrypt).
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()


class AuthError(Exception):
    pass


class Store:
    def __init__(self, path=APP_DB):
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self._lock = threading.Lock()

    def _x(self, sql, params=()):
        with self._lock, self.con:
            return self.con.execute(sql, params)

    # accounts ----------------------------------------------------------------------------------
    def create_user(self, email, password, is_admin=False):
        email = email.strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise AuthError("enter a valid email address")
        if len(password) < 8:
            raise AuthError("password must be at least 8 characters")
        salt = secrets.token_hex(16)
        try:
            cur = self._x("INSERT INTO users (email, pw_hash, pw_salt, is_admin, created_at) VALUES (?,?,?,?,?)",
                          (email, _hash(password, salt), salt, int(is_admin), now().isoformat()))
        except sqlite3.IntegrityError:
            raise AuthError("an account with that email already exists") from None
        return self.user(cur.lastrowid)

    def login(self, email, password):
        row = self._x("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        if not row or not hmac.compare_digest(row["pw_hash"], _hash(password, row["pw_salt"])):
            raise AuthError("wrong email or password")
        token = secrets.token_urlsafe(32)
        self._x("INSERT INTO sessions VALUES (?,?,?)",
                (token, row["id"], (now() + datetime.timedelta(days=SESSION_DAYS)).isoformat()))
        return token, self.user(row["id"])

    def logout(self, token):
        self._x("DELETE FROM sessions WHERE token = ?", (token,))

    def user_for_token(self, token):
        if not token:
            return None
        row = self._x("SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row or row["expires_at"] < now().isoformat():
            return None
        return self.user(row["user_id"])

    def user(self, user_id):
        row = self._x("SELECT id, email, is_admin, plan, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def ensure_admin(self, email, password):
        """Create the admin account from ADMIN_EMAIL / ADMIN_PASSWORD if it doesn't exist."""
        if not self._x("SELECT 1 FROM users WHERE email = ?", (email.lower(),)).fetchone():
            self.create_user(email, password, is_admin=True)

    # questions ---------------------------------------------------------------------------------
    def questions_today(self, user_id):
        start = now().replace(hour=0, minute=0, second=0).isoformat()
        return self._x("SELECT COUNT(*) FROM answers WHERE user_id = ? AND kind = 'ask' AND created_at >= ?",
                       (user_id, start)).fetchone()[0]

    def save_answer(self, user_id, thread_id, kind, question, payload, seconds=None):
        aid = secrets.token_urlsafe(9)
        self._x("INSERT INTO answers VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            aid, user_id, thread_id, kind, question, json.dumps(payload, default=str),
            int(bool(payload.get("can_answer"))), payload.get("usage", {}).get("usd", 0), seconds,
            payload.get("error"), now().isoformat()))
        return aid

    def answer(self, answer_id):
        row = self._x("SELECT * FROM answers WHERE id = ?", (answer_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        return d

    def history(self, user_id, limit=30):
        rows = self._x("SELECT id, thread_id, kind, question, can_answer, created_at FROM answers "
                       "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # saved and shared --------------------------------------------------------------------------
    def save(self, user_id, answer_id, title, list_name="Saved"):
        self._x("INSERT OR REPLACE INTO saved (user_id, answer_id, title, list_name, created_at) VALUES (?,?,?,?,?)",
                (user_id, answer_id, title[:200], list_name[:80] or "Saved", now().isoformat()))

    def unsave(self, user_id, answer_id):
        self._x("DELETE FROM saved WHERE user_id = ? AND answer_id = ?", (user_id, answer_id))

    def saved(self, user_id):
        rows = self._x("SELECT s.answer_id, s.title, s.list_name, s.created_at, a.question FROM saved s "
                       "JOIN answers a ON a.id = s.answer_id WHERE s.user_id = ? ORDER BY s.list_name, s.created_at DESC",
                       (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def share(self, answer_id, user_id):
        row = self._x("SELECT token FROM shares WHERE answer_id = ?", (answer_id,)).fetchone()
        if row:
            return row["token"]
        token = secrets.token_urlsafe(12)
        self._x("INSERT INTO shares VALUES (?,?,?,?)", (token, answer_id, user_id, now().isoformat()))
        return token

    def shared_answer(self, token):
        row = self._x("SELECT answer_id FROM shares WHERE token = ?", (token,)).fetchone()
        return self.answer(row["answer_id"]) if row else None

    # reports and admin -------------------------------------------------------------------------
    def report(self, answer_id, user_id, comment):
        self._x("INSERT INTO reports (answer_id, user_id, comment, created_at) VALUES (?,?,?,?)",
                (answer_id, user_id, comment[:2000], now().isoformat()))

    def set_report_status(self, report_id, status):
        self._x("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))

    def admin_stats(self, days=30):
        since = (now() - datetime.timedelta(days=days)).isoformat()
        q = lambda sql, p=(): [dict(r) for r in self._x(sql, p).fetchall()]  # noqa: E731
        return {
            "totals": q("SELECT COUNT(*) AS questions, SUM(can_answer) AS answered, ROUND(SUM(usd), 2) AS usd, "
                        "COUNT(DISTINCT user_id) AS active_users, ROUND(AVG(seconds), 1) AS avg_seconds "
                        "FROM answers WHERE kind = 'ask' AND created_at >= ?", (since,))[0],
            "per_day": q("SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS questions, ROUND(SUM(usd), 2) AS usd "
                         "FROM answers WHERE kind = 'ask' AND created_at >= ? GROUP BY 1 ORDER BY 1", (since,)),
            "popular": q("SELECT lower(question) AS question, COUNT(*) AS n FROM answers WHERE kind = 'ask' AND "
                         "created_at >= ? GROUP BY 1 ORDER BY n DESC LIMIT 15", (since,)),
            "cant_answer": q("SELECT id, question, error, created_at FROM answers WHERE kind = 'ask' AND can_answer = 0 "
                             "ORDER BY created_at DESC LIMIT 20"),
            "reports": q("SELECT r.id, r.answer_id, r.comment, r.status, r.created_at, u.email, a.question "
                         "FROM reports r JOIN answers a ON a.id = r.answer_id LEFT JOIN users u ON u.id = r.user_id "
                         "ORDER BY r.status = 'open' DESC, r.created_at DESC LIMIT 50"),
            "users": q("SELECT u.id, u.email, u.plan, u.is_admin, u.created_at, COUNT(a.id) AS questions "
                       "FROM users u LEFT JOIN answers a ON a.user_id = u.id AND a.kind = 'ask' "
                       "GROUP BY u.id ORDER BY questions DESC LIMIT 100"),
        }


def default_store():
    os.makedirs(APP_DB.parent, exist_ok=True)
    return Store(APP_DB)
