"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, type AdminStats } from "@/lib/api";
import { useRequireUser } from "@/components/use-require-user";

export default function AdminPage() {
  const { user } = useRequireUser();
  const [d, setD] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.admin().then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load."));
  useEffect(() => {
    if (user) load();
  }, [user]);

  if (!user) return null;
  if (!user.is_admin) return <p className="text-muted">Admins only.</p>;
  if (error) return <p className="text-bad">{error}</p>;
  if (!d) return <p className="text-muted">Loading…</p>;

  const t = d.totals;
  const tiles = [
    ["Questions (30 days)", t.questions ?? 0],
    ["Answered", t.questions ? `${Math.round((100 * (t.answered ?? 0)) / t.questions)}%` : "-"],
    ["Active users", t.active_users ?? 0],
    ["AI spend", `$${(t.usd ?? 0).toFixed(2)}`],
    ["Avg time", t.avg_seconds ? `${t.avg_seconds}s` : "-"],
  ];

  async function setStatus(id: number, status: "open" | "resolved" | "wontfix") {
    await api.setReport(id, status);
    load();
  }

  return (
    <div className="space-y-10">
      <h1 className="font-serif text-2xl font-bold">Admin</h1>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-px bg-rule border border-rule">
        {tiles.map(([k, v], i) => (
          <div key={k} className={`bg-surface p-4 ${i === tiles.length - 1 ? "col-span-2 sm:col-span-1" : ""}`}>
            <p className="text-xs uppercase tracking-wider text-muted">{k}</p>
            <p className="font-serif text-2xl font-bold mt-1 tabular-nums">{v}</p>
          </div>
        ))}
      </div>

      <section>
        <h2 className="font-serif text-xl font-bold mb-3">Issue reports</h2>
        {d.reports.length === 0 ? <p className="text-sm text-muted">None yet.</p> : (
          <div className="overflow-x-auto">
            <table className="stats-table text-sm">
              <thead><tr><th>When</th><th>Question</th><th>Report</th><th>From</th><th>Status</th></tr></thead>
              <tbody>
                {d.reports.map((r) => (
                  <tr key={r.id}>
                    <td className="text-muted">{r.created_at.slice(0, 10)}</td>
                    <td className="whitespace-normal min-w-48"><Link href={`/a/${r.answer_id}`} className="text-accent hover:underline">{r.question}</Link></td>
                    <td className="whitespace-normal min-w-48">{r.comment}</td>
                    <td className="text-muted">{r.email ?? "-"}</td>
                    <td>
                      <select value={r.status} onChange={(e) => setStatus(r.id, e.target.value as "open" | "resolved" | "wontfix")}
                              className={`border border-rule bg-surface px-2 py-1 ${r.status === "open" ? "font-semibold text-bad" : ""}`}>
                        <option value="open">open</option><option value="resolved">resolved</option><option value="wontfix">won&apos;t fix</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="grid md:grid-cols-2 gap-10">
        <section>
          <h2 className="font-serif text-xl font-bold mb-3">Popular questions</h2>
          <ol className="divide-y divide-rule border-y border-rule text-sm">
            {d.popular.map((p) => <li key={p.question} className="py-2 flex justify-between gap-3"><span>{p.question}</span><span className="text-muted tabular-nums">{p.n}</span></li>)}
          </ol>
        </section>
        <section>
          <h2 className="font-serif text-xl font-bold mb-3">Couldn&apos;t answer</h2>
          <ul className="divide-y divide-rule border-y border-rule text-sm">
            {d.cant_answer.map((c) => (
              <li key={c.id} className="py-2">
                <Link href={`/a/${c.id}`} className="hover:text-accent">{c.question}</Link>
                <span className="text-muted text-xs"> · {c.created_at.slice(0, 10)}{c.error ? ` · ${c.error}` : ""}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section>
        <h2 className="font-serif text-xl font-bold mb-3">Users</h2>
        <div className="overflow-x-auto">
          <table className="stats-table text-sm">
            <thead><tr><th>Email</th><th>Plan</th><th>Joined</th><th className="num">Questions</th></tr></thead>
            <tbody>
              {d.users.map((u) => (
                <tr key={u.id}><td>{u.email}{u.is_admin ? " (admin)" : ""}</td><td>{u.plan}</td><td className="text-muted">{u.created_at.slice(0, 10)}</td><td className="num">{u.questions}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="font-serif text-xl font-bold mb-3">Questions per day</h2>
        <table className="stats-table text-sm max-w-md">
          <thead><tr><th>Day</th><th className="num">Questions</th><th className="num">Spend</th></tr></thead>
          <tbody>{d.per_day.map((p) => <tr key={p.day}><td>{p.day}</td><td className="num">{p.questions}</td><td className="num">${p.usd.toFixed(2)}</td></tr>)}</tbody>
        </table>
      </section>
    </div>
  );
}
