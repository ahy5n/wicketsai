"""Run the accuracy suite (eval/questions.yaml) against the engine and report.

    .venv/bin/python eval/run_eval.py --limit 10              # quick sample (costs real money)
    .venv/bin/python eval/run_eval.py --max-usd 20            # full suite with a spend cap
    .venv/bin/python eval/run_eval.py --ids career_runs_kohli refuse_ipl

Pass bar for the demo (brief, week 2): 80%+ correct, and failures say "can't answer" rather than guess.
Results go to eval/results/<timestamp>/ (answers.jsonl + report.md).
"""
import argparse
import concurrent.futures as cf
import datetime
import json
import re
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from wickets.db import Database  # noqa: E402

NUM = re.compile(r"-?\d[\d,]*\.?\d*")


class Grader:
    def __init__(self, db):
        self.db = db
        self._aliases = {}

    def gold(self, q):
        r = self.db.query(q["gold_sql"], max_rows=50)
        return r.rows[0] if q["grade"] == "scalar" else [row[0] for row in r.rows]

    def aliases(self, name):
        """Every way a name in a gold list may be written: scorecard, unique and full name."""
        if name not in self._aliases:
            rows = self.db.con.execute(
                "SELECT name, unique_name, full_name FROM player_index WHERE name = ? OR unique_name = ?",
                [name, name]).fetchall()
            self._aliases[name] = {str(name).lower()} | {str(v).lower() for r in rows for v in r if v}
        return self._aliases[name]

    def grade(self, q, ans):
        """-> (correct: bool, detail: str)"""
        if q["grade"] == "refuse":
            return (not ans["can_answer"]), "refused" if not ans["can_answer"] else "answered a question it should refuse"
        if not ans["can_answer"]:
            return False, f"said it can't answer: {ans['answer'][:120]}"
        gold = self.gold(q)
        cells = [c for row in (ans.get("table") or {}).get("rows", []) for c in row]
        text = ans["answer"]
        if q["grade"] == "scalar":
            missing = [g for g in gold if not _found(g, cells, text)]
            return (not missing), "ok" if not missing else f"expected {gold}, missing {missing}"
        # list: every gold item appears among the answer's top rows or in the sentence
        rows = (ans.get("table") or {}).get("rows", [])[: len(gold) + 3]
        hay = " | ".join(str(c).lower() for row in rows for c in row) + " | " + text.lower()
        missing = [g for g in gold if not any(a in hay for a in self.aliases(g))]
        return (not missing), "ok" if not missing else f"expected {gold}, missing {missing}"

    @staticmethod
    def disclosed(q, ans):
        if "expect_note" not in q:
            return None
        blob = " ".join(ans.get("coverage_notes", []) + ans.get("assumptions", []) + [ans["answer"]]).lower()
        return q["expect_note"].lower() in blob


def _found(gold, cells, text):
    if isinstance(gold, bool) or gold is None:
        return False
    if isinstance(gold, (int, float)):
        nums = [c for c in cells if isinstance(c, (int, float)) and not isinstance(c, bool)]
        nums += [float(n.replace(",", "")) for n in NUM.findall(text) if n.replace(",", "").replace(".", "").lstrip("-").isdigit()]
        for n in nums:
            if isinstance(gold, int) and float(gold).is_integer():
                if abs(n - gold) < 1e-9:
                    return True
            elif abs(n - gold) <= 0.051:  # the same rate rounded to 1 dp instead of 2
                return True
        return False
    g = str(gold).lower()
    return any(g in str(c).lower() for c in cells) or g in text.lower()


def run_one(engine, grader, q):
    conv = engine.conversation()
    start = time.time()
    for turn in q["turns"]:
        a = conv.ask(turn).to_dict()
    ok, detail = grader.grade(q, a)
    return {"id": q["id"], "category": q["category"], "question": " / ".join(q["turns"]),
            "correct": ok, "detail": detail, "disclosed": grader.disclosed(q, a),
            "seconds": round(time.time() - start, 1), "usd": a["usage"].get("usd", 0), "answer": a}


def report(results, out_dir, args):
    n = len(results)
    correct = sum(r["correct"] for r in results)
    by_cat = defaultdict(lambda: [0, 0])
    for r in results:
        by_cat[r["category"]][0] += r["correct"]
        by_cat[r["category"]][1] += 1
    disc = [r for r in results if r["disclosed"] is not None]
    wrong_answers = [r for r in results if not r["correct"] and r["answer"]["can_answer"]]
    false_refusals = [r for r in results if not r["correct"] and not r["answer"]["can_answer"]]
    usd = sum(r["usd"] for r in results)
    lines = [
        f"# Wickets.ai accuracy suite: {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"Model `{args.model}`, effort `{args.effort}`.",
        "",
        f"**Correct: {correct}/{n} ({100 * correct / n:.1f}%)**. Bar: 80%.",
        f"- Wrong answers given confidently: {len(wrong_answers)} (these are the dangerous ones)",
        f"- Said \"can't answer\" when it could have: {len(false_refusals)}",
        f"- Coverage gaps disclosed: {sum(r['disclosed'] for r in disc)}/{len(disc)}",
        f"- Cost: ${usd:.2f} total, ${usd / n:.3f} per question; median {sorted(r['seconds'] for r in results)[n // 2]}s",
        "", "| Category | Correct |", "|---|---|",
        *[f"| {c} | {a}/{b} |" for c, (a, b) in sorted(by_cat.items())],
        "", "## Failures", "",
        *[f"- `{r['id']}` {r['question']}\n  - {r['detail']}\n  - answer: {r['answer']['answer'][:200]}\n"
          f"  - sql: `{(r['answer'].get('sql') or '')[:300]}`" for r in results if not r["correct"]],
        "", "## Disclosure misses", "",
        *[f"- `{r['id']}` notes: {r['answer'].get('coverage_notes')}" for r in disc if not r["disclosed"]],
    ]
    (out_dir / "report.md").write_text("\n".join(lines))
    return "\n".join(lines[:12 + len(by_cat) + 3])


def main():
    from wickets.engine import EFFORT, MODEL, Engine
    from wickets.settings import require_api_key

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-usd", type=float, default=25.0, help="stop starting new questions past this spend")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default=EFFORT)
    args = ap.parse_args()
    require_api_key()

    qs = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())
    if args.ids:
        qs = [q for q in qs if q["id"] in set(args.ids)]
    if args.limit:
        step = max(1, len(qs) // args.limit)  # spread the sample across categories
        qs = qs[::step][: args.limit]

    db = Database()
    engine = Engine(db=db, model=args.model, effort=args.effort)
    grader = Grader(db)
    out_dir = ROOT / "eval" / "results" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True)
    spent, lock, results = 0.0, threading.Lock(), []

    def task(q):
        nonlocal spent
        with lock:
            if spent >= args.max_usd:
                return None
        r = run_one(engine, grader, q)
        with lock:
            spent += r["usd"]
            results.append(r)
            with (out_dir / "answers.jsonl").open("a") as f:
                f.write(json.dumps(r, default=str) + "\n")
            print(f"[{len(results):3}/{len(qs)}] {'PASS' if r['correct'] else 'FAIL'} {r['id']:34} "
                  f"${r['usd']:.3f} {r['seconds']}s  (total ${spent:.2f})", flush=True)
        return r

    with cf.ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(task, qs))
    if len(results) < len(qs):
        print(f"stopped at the ${args.max_usd} cap after {len(results)} questions")
    print(report(results, out_dir, args))
    print(f"\nFull report: {out_dir / 'report.md'}")


if __name__ == "__main__":
    main()
