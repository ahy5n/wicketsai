"use client";

import { useRef, useState } from "react";
import { toPng } from "html-to-image";
import { api, type Answer } from "@/lib/api";
import { AnswerChart, chartSpec } from "./answer-chart";

function fmt(v: string | number | null) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-GB") : v.toLocaleString("en-GB", { maximumFractionDigits: 2 });
  return v;
}

const label = (c: string) => c.replaceAll("_", " ");

export function StatsTable({ answer }: { answer: Answer }) {
  const t = answer.table;
  if (!t || t.rows.length === 0) return null;
  const numeric = t.columns.map((_, i) => t.rows.every((r) => typeof r[i] === "number" || r[i] === null));
  return (
    <div className="overflow-x-auto -mx-1 px-1">
      <table className="stats-table text-[15px]">
        <thead>
          <tr>{t.columns.map((c, i) => <th key={c} className={numeric[i] ? "num" : ""}>{label(c)}</th>)}</tr>
        </thead>
        <tbody>
          {t.rows.slice(0, 50).map((r, ri) => (
            <tr key={ri}>{r.map((v, i) => <td key={i} className={numeric[i] ? "num" : ""}>{fmt(v)}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {(t.rows.length > 50 || t.truncated) && <p className="text-xs text-muted mt-2">Showing the first 50 rows; the CSV has all of them.</p>}
    </div>
  );
}

export function AnswerCard({ answer, owned = true }: { answer: Answer; owned?: boolean }) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [proofOpen, setProofOpen] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [reporting, setReporting] = useState(false);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState(answer.question);
  const [list, setList] = useState("Saved");
  const [capturing, setCapturing] = useState(false);

  const chartable = (answer.display === "bar" || answer.display === "line") && chartSpec(answer.table);
  const showTable = answer.table && !(answer.display === "sentence" && answer.table.rows.length === 1 && answer.table.columns.length <= 2);

  async function share() {
    const { token } = await api.share(answer.id);
    const url = `${location.origin}/s/${token}`;
    await navigator.clipboard?.writeText(url).catch(() => {});
    setStatus(`Share link copied: ${url}`);
  }

  async function png() {
    if (!cardRef.current) return;
    setCapturing(true);
    try {
      await new Promise((r) => requestAnimationFrame(() => r(null)));
      const bg = getComputedStyle(document.body).backgroundColor;
      const dataUrl = await toPng(cardRef.current, { backgroundColor: bg, pixelRatio: 2, filter: (n) => !(n instanceof HTMLElement && n.dataset.noExport) });
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = `wickets-${answer.id}.png`;
      a.click();
    } finally {
      setCapturing(false);
    }
  }

  async function save() {
    await api.save(answer.id, title, list);
    setSaving(false);
    setStatus(`Saved to “${list}”.`);
  }

  async function report() {
    await api.report(answer.id, comment);
    setReporting(false);
    setComment("");
    setStatus("Thanks: the report is with the Wickets.ai team.");
  }

  return (
    <article className="bg-surface border border-rule rounded-sm">
      <div ref={cardRef} className="p-5 sm:p-7">
        <p className="text-xs uppercase tracking-wider text-muted mb-2">{answer.question}</p>
        <p className={`font-serif leading-snug ${answer.can_answer ? "text-2xl sm:text-[1.7rem] text-ink" : "text-xl text-muted"}`}>
          {answer.answer}
        </p>

        {answer.can_answer && chartable && <AnswerChart table={answer.table!} kind={answer.display as "bar" | "line"} />}
        {answer.can_answer && showTable && <div className="mt-5"><StatsTable answer={answer} /></div>}

        {(answer.assumptions.length > 0 || answer.coverage_notes.length > 0) && (
          <div className="mt-5 space-y-2 text-sm">
            {answer.assumptions.map((a, i) => (
              <p key={`a${i}`} className="text-muted"><span className="font-semibold text-ink">Assumption:</span> {a}</p>
            ))}
            {answer.coverage_notes.map((n, i) => (
              <p key={`c${i}`} className="bg-warn-bg text-warn-ink px-3 py-2 rounded-sm"><span className="font-semibold">Coverage:</span> {n}</p>
            ))}
          </div>
        )}

        {capturing && (
          <p className="mt-6 pt-3 border-t border-rule text-xs text-muted flex justify-between">
            <span className="font-serif font-bold text-ink">Wickets<span className="text-accent">.ai</span></span>
            <span>Data from Cricsheet</span>
          </p>
        )}
      </div>

      {answer.evidence && (
        <div className="border-t border-rule px-5 sm:px-7">
          <button onClick={() => setProofOpen((o) => !o)} className="w-full py-3 flex justify-between items-center text-sm focus-ring" aria-expanded={proofOpen}>
            <span>
              <span className="font-semibold">Proof</span>
              <span className="text-muted">
                {" "}· {answer.evidence.match_count.toLocaleString("en-GB")} matches
                {answer.evidence.balls ? ` · ${answer.evidence.balls.toLocaleString("en-GB")} balls` : ""}
                {answer.evidence.first_date ? ` · ${answer.evidence.first_date} to ${answer.evidence.last_date}` : ""}
              </span>
            </span>
            <span className="text-muted">{proofOpen ? "Hide" : "Show"}</span>
          </button>
          {proofOpen && (
            <div className="pb-5 space-y-4 text-sm">
              {answer.sql && (
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted mb-1">Query</p>
                  <pre className="bg-bg border border-rule p-3 overflow-x-auto text-xs leading-relaxed whitespace-pre-wrap break-words">{answer.sql}</pre>
                </div>
              )}
              <div>
                <p className="text-xs uppercase tracking-wider text-muted mb-1">
                  Matches{answer.evidence.match_count > answer.evidence.matches.length ? ` (latest ${answer.evidence.matches.length})` : ""}
                </p>
                <ul className="divide-y divide-rule border-y border-rule">
                  {answer.evidence.matches.map((m) => (
                    <li key={m.match_id} className="py-1.5 flex gap-3">
                      <span className="text-muted tabular-nums shrink-0">{m.date}</span>
                      <a href={m.url} target="_blank" rel="noreferrer" className="text-accent hover:underline truncate">{m.fixture}</a>
                      {m.event && <span className="text-muted truncate hidden sm:inline">{m.event}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}

      {owned && (
        <div className="border-t border-rule px-5 sm:px-7 py-3 flex flex-wrap gap-x-5 gap-y-2 text-sm" data-no-export="1">
          <button className="text-accent font-semibold focus-ring" onClick={() => setSaving((s) => !s)}>Save</button>
          <button className="text-accent font-semibold focus-ring" onClick={share}>Share link</button>
          {answer.table && <a className="text-accent font-semibold focus-ring" href={`/api/answers/${answer.id}/export.csv`}>CSV</a>}
          <button className="text-accent font-semibold focus-ring" onClick={png}>PNG</button>
          <button className="text-muted hover:text-bad ml-auto focus-ring" onClick={() => setReporting((r) => !r)}>Report an issue</button>
        </div>
      )}

      {saving && (
        <form className="border-t border-rule px-5 sm:px-7 py-4 flex flex-col sm:flex-row gap-2" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <input className="flex-1 border border-rule bg-bg px-3 py-2 focus-ring" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Title" />
          <input className="sm:w-44 border border-rule bg-bg px-3 py-2 focus-ring" value={list} onChange={(e) => setList(e.target.value)} aria-label="List" placeholder="List name" />
          <button className="bg-accent text-accent-ink px-4 py-2 font-semibold focus-ring">Save</button>
        </form>
      )}

      {reporting && (
        <form className="border-t border-rule px-5 sm:px-7 py-4 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); report(); }}>
          <label className="text-sm text-muted" htmlFor={`rep-${answer.id}`}>What looks wrong? Include the figure you expected and your source if you have one.</label>
          <textarea id={`rep-${answer.id}`} className="border border-rule bg-bg px-3 py-2 min-h-20 focus-ring" value={comment} onChange={(e) => setComment(e.target.value)} required minLength={3} />
          <button className="self-start bg-ink text-bg px-4 py-2 font-semibold focus-ring">Send report</button>
        </form>
      )}

      {status && <p className="border-t border-rule px-5 sm:px-7 py-2 text-sm text-muted break-all" role="status">{status}</p>}
    </article>
  );
}
