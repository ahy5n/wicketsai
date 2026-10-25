"""Ask Wickets.ai from the terminal.

    .venv/bin/python -m wickets "How many sixes has Suryakumar Yadav hit off spinners?"
    .venv/bin/python -m wickets            # interactive; follow-ups keep context
    .venv/bin/python -m wickets --json "..."
"""
import argparse
import json
import sys

from .engine import Engine
from .settings import require_api_key


def render(a):
    out = [f"\n{a.answer}\n"]
    if a.table:
        cols, rows = a.table["columns"], a.table["rows"][:25]
        widths = [max(len(str(c)), *(len(_fmt(r[i])) for r in rows)) for i, c in enumerate(cols)]
        out.append("  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
        out.append("  ".join("-" * w for w in widths))
        out += ["  ".join(_fmt(v).ljust(w) for v, w in zip(r, widths)) for r in rows]
        if len(a.table["rows"]) > 25 or a.table.get("truncated"):
            out.append(f"... {len(a.table['rows'])} rows")
        out.append("")
    for note in a.assumptions:
        out.append(f"Assumption: {note}")
    for note in a.coverage_notes:
        out.append(f"Coverage: {note}")
    if a.evidence:
        ev = a.evidence
        balls = f", {ev['balls']:,} balls" if ev.get("balls") else ""
        out.append(f"\nProof: {ev['match_count']:,} matches{balls}"
                   + (f" ({ev['first_date']} to {ev['last_date']})" if ev.get("first_date") else ""))
        for m in ev["matches"][:5]:
            out.append(f"  {m['date']}  {m['fixture']:<34} {m['url']}")
        if ev["match_count"] > 5:
            out.append(f"  ... and {ev['match_count'] - 5:,} more")
    if a.sql:
        out.append(f"\nSQL:\n{a.sql}")
    if a.error:
        out.append(f"\n[{a.error}]")
    out.append(f"\n({a.usage.get('usd', 0):.3f} USD, {len(a.trace)} tool calls)")
    return "\n".join(out)


def _fmt(v):
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v):,}"
    if isinstance(v, int):
        return f"{v:,}" if abs(v) >= 10000 else str(v)
    return "" if v is None else str(v)


def main():
    ap = argparse.ArgumentParser(description="Ask a T20I question")
    ap.add_argument("question", nargs="*")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    require_api_key()
    conv = Engine().conversation()
    questions = [" ".join(args.question)] if args.question else iter(lambda: input("\nAsk> "), "")
    for q in questions:
        a = conv.ask(q)
        print(json.dumps(a.to_dict(), indent=2, default=str) if args.json else render(a))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
