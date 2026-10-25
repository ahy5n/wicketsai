"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useRequireUser } from "@/components/use-require-user";

type Saved = Awaited<ReturnType<typeof api.saved>>["items"];
type History = Awaited<ReturnType<typeof api.history>>["items"];

export default function SavedPage() {
  const { user } = useRequireUser();
  const [saved, setSaved] = useState<Saved | null>(null);
  const [history, setHistory] = useState<History | null>(null);

  useEffect(() => {
    if (!user) return;
    api.saved().then((r) => setSaved(r.items));
    api.history().then((r) => setHistory(r.items));
  }, [user]);

  async function remove(id: string) {
    await api.unsave(id);
    setSaved((s) => s?.filter((x) => x.answer_id !== id) ?? null);
  }

  const lists = new Map<string, Saved>();
  for (const s of saved ?? []) lists.set(s.list_name, [...(lists.get(s.list_name) ?? []), s]);

  return (
    <div className="grid md:grid-cols-2 gap-10">
      <section>
        <h1 className="font-serif text-2xl font-bold mb-4">Saved</h1>
        {saved && saved.length === 0 && <p className="text-muted text-sm">Nothing saved yet. Use “Save” on any answer to build a stat list.</p>}
        {[...lists.entries()].map(([name, items]) => (
          <div key={name} className="mb-6">
            <h2 className="text-xs uppercase tracking-wider text-muted mb-2">{name}</h2>
            <ul className="divide-y divide-rule border-y border-rule">
              {items.map((s) => (
                <li key={s.answer_id} className="py-2.5 flex gap-3 items-start">
                  <Link href={`/a/${s.answer_id}`} className="flex-1 hover:text-accent">{s.title}</Link>
                  <button onClick={() => remove(s.answer_id)} className="text-xs text-muted hover:text-bad focus-ring">Remove</button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
      <section>
        <h2 className="font-serif text-2xl font-bold mb-4">Recent</h2>
        <ul className="divide-y divide-rule border-y border-rule">
          {history?.map((h) => (
            <li key={h.id} className="py-2.5">
              <Link href={`/a/${h.id}`} className="hover:text-accent">{h.question}</Link>
              <p className="text-xs text-muted mt-0.5">
                {h.kind === "filter" ? "Filter" : "Question"} · {new Date(h.created_at).toLocaleString("en-GB")}
                {!h.can_answer && " · couldn't answer"}
              </p>
            </li>
          ))}
        </ul>
        {history && history.length === 0 && <p className="text-muted text-sm">Your questions will appear here.</p>}
      </section>
    </div>
  );
}
