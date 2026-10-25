"""Read-only access to the Wickets.ai DuckDB database.

Three independent locks keep model-written SQL harmless: the connection is opened read_only, external
file/network access is disabled, and every statement must parse as a single SELECT. Queries are capped
in time and rows.
"""
import datetime
import decimal
import threading
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "wickets.duckdb"
QUERY_TIMEOUT_S = 15
MAX_ROWS = 500


class QueryError(Exception):
    pass


@dataclass
class Result:
    columns: list
    rows: list
    truncated: bool = False
    row_count: int = 0
    elapsed_s: float = 0.0
    notes: list = field(default_factory=list)

    def as_dicts(self):
        return [dict(zip(self.columns, r)) for r in self.rows]


def _jsonable(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


class Database:
    def __init__(self, path=DB_PATH):
        self.con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": False})
        try:
            self.con.execute("SET lock_configuration = true")
        except duckdb.InvalidInputException:
            pass  # another connection to the same file in this process already locked it
        self._lock = threading.Lock()

    def check(self, sql):
        sql = (sql or "").strip().rstrip(";").strip()
        if not sql:
            raise QueryError("empty query")
        try:
            statements = self.con.extract_statements(sql)
        except duckdb.Error as e:
            raise QueryError(f"SQL parse error: {e}") from None
        if len(statements) != 1:
            raise QueryError("send exactly one statement")
        if statements[0].type != duckdb.StatementType.SELECT:
            raise QueryError(f"only SELECT queries are allowed (got {statements[0].type.name})")
        return sql

    def query(self, sql, max_rows=MAX_ROWS, timeout_s=QUERY_TIMEOUT_S, params=None):
        sql = self.check(sql)
        with self._lock:
            timer = threading.Timer(timeout_s, self.con.interrupt)
            start = datetime.datetime.now()
            timer.start()
            try:
                cur = self.con.execute(sql, params or [])
                columns = [d[0] for d in cur.description]
                rows = cur.fetchmany(max_rows + 1)
            except duckdb.InterruptException:
                raise QueryError(f"query took longer than {timeout_s}s; simplify or aggregate it") from None
            except duckdb.Error as e:
                raise QueryError(f"{type(e).__name__}: {e}") from None
            finally:
                timer.cancel()
        truncated = len(rows) > max_rows
        rows = [[_jsonable(v) for v in r] for r in rows[:max_rows]]
        elapsed = (datetime.datetime.now() - start).total_seconds()
        return Result(columns, rows, truncated, len(rows), round(elapsed, 3))
