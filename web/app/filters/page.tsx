"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Answer, type Meta, type PlayerHit } from "@/lib/api";
import { AnswerCard } from "@/components/answer-card";
import { useRequireUser } from "@/components/use-require-user";

type F = {
  perspective: "batting" | "bowling";
  player?: PlayerHit | null;
  gender?: string;
  opponent?: string;
  venue_id?: string;
  date_from?: string;
  date_to?: string;
  phases: string[];
  bowling_kind?: string;
  bowling_type?: string;
  batting_hand?: string;
  batting_position?: string;
  group_by: string;
};

const GROUP_LABELS: Record<string, string> = {
  none: "No split", year: "Year", opponent: "Opponent", phase: "Phase", bowling_type: "Bowling type",
  batting_hand: "Batting hand", venue: "Venue",
};

const field = "w-full border border-rule bg-surface px-3 py-2 focus-ring";
const lbl = "text-xs uppercase tracking-wider text-muted";

export default function FiltersPage() {
  const { user } = useRequireUser();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [f, setF] = useState<F>({ perspective: "batting", phases: [], group_by: "none" });
  const [result, setResult] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) api.meta().then(setMeta);
  }, [user]);

  const set = <K extends keyof F>(k: K, v: F[K]) => setF((x) => ({ ...x, [k]: v }));

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { perspective: f.perspective, group_by: f.group_by };
    if (f.player) body.player_id = f.player.player_id;
    for (const k of ["gender", "opponent", "date_from", "date_to", "bowling_kind", "bowling_type", "batting_hand"] as const) {
      if (f[k]) body[k] = f[k];
    }
    if (f.venue_id) body.venue_id = Number(f.venue_id);
    if (f.batting_position) body.batting_position = Number(f.batting_position);
    if (f.phases.length) body.phases = f.phases;
    try {
      const a = await api.query(body);
      // Charts for splits: a line over years, bars for categories.
      if (f.group_by !== "none") a.display = f.group_by === "year" ? "line" : "bar";
      setResult(a);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That filter couldn't be run.");
    } finally {
      setBusy(false);
    }
  }

  if (!user) return null;

  return (
    <div className="grid lg:grid-cols-[20rem_1fr] gap-8">
      <form onSubmit={run} className="space-y-4">
        <h1 className="font-serif text-2xl font-bold">Filter builder</h1>
        <p className="text-sm text-muted -mt-2">Free and instant: these queries don&apos;t use your question allowance.</p>

        <div className="flex border border-ink" role="radiogroup" aria-label="Perspective">
          {(["batting", "bowling"] as const).map((p) => (
            <button type="button" key={p} role="radio" aria-checked={f.perspective === p} onClick={() => set("perspective", p)}
                    className={`flex-1 py-2 text-sm font-semibold capitalize focus-ring ${f.perspective === p ? "bg-ink text-bg" : ""}`}>
              {p}
            </button>
          ))}
        </div>

        <PlayerPicker value={f.player ?? null} onChange={(p) => set("player", p)} gender={f.gender} />

        <div className="grid grid-cols-2 gap-3">
          <label className="block"><span className={lbl}>Gender</span>
            <select className={field} value={f.gender ?? ""} onChange={(e) => set("gender", e.target.value || undefined)}>
              <option value="">Both</option><option value="male">Men</option><option value="female">Women</option>
            </select>
          </label>
          <label className="block"><span className={lbl}>Opponent</span>
            <select className={field} value={f.opponent ?? ""} onChange={(e) => set("opponent", e.target.value || undefined)}>
              <option value="">Any</option>
              {meta?.teams.map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
        </div>

        <label className="block"><span className={lbl}>Venue</span>
          <select className={field} value={f.venue_id ?? ""} onChange={(e) => set("venue_id", e.target.value || undefined)}>
            <option value="">Any</option>
            {meta?.venues.map((v) => <option key={v.id} value={v.id}>{v.name}{v.city ? `, ${v.city}` : ""}</option>)}
          </select>
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block"><span className={lbl}>From</span>
            <input type="date" className={field} value={f.date_from ?? ""} onChange={(e) => set("date_from", e.target.value || undefined)} />
          </label>
          <label className="block"><span className={lbl}>To</span>
            <input type="date" className={field} value={f.date_to ?? ""} onChange={(e) => set("date_to", e.target.value || undefined)} />
          </label>
        </div>

        <fieldset>
          <legend className={lbl}>Phase</legend>
          <div className="flex gap-2 mt-1">
            {["powerplay", "middle", "death"].map((p) => {
              const on = f.phases.includes(p);
              return (
                <button type="button" key={p} aria-pressed={on}
                        onClick={() => set("phases", on ? f.phases.filter((x) => x !== p) : [...f.phases, p])}
                        className={`flex-1 py-1.5 text-sm border capitalize focus-ring ${on ? "bg-accent text-accent-ink border-accent" : "border-rule"}`}>
                  {p}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-muted mt-1">Overs 1-6, 7-15, 16-20.</p>
        </fieldset>

        <div className="grid grid-cols-2 gap-3">
          <label className="block"><span className={lbl}>Bowling</span>
            <select className={field} value={f.bowling_kind ?? ""} onChange={(e) => set("bowling_kind", e.target.value || undefined)}>
              <option value="">Any</option><option value="pace">Pace</option><option value="spin">Spin</option>
            </select>
          </label>
          <label className="block"><span className={lbl}>Bowling type</span>
            <select className={field} value={f.bowling_type ?? ""} onChange={(e) => set("bowling_type", e.target.value || undefined)}>
              <option value="">Any</option>
              {meta?.bowling_types.map((t) => <option key={t} value={t}>{t === "orthodox" ? "left-arm orthodox" : t === "wrist-spin" ? "left-arm wrist spin" : t}</option>)}
            </select>
          </label>
          <label className="block"><span className={lbl}>Batting hand</span>
            <select className={field} value={f.batting_hand ?? ""} onChange={(e) => set("batting_hand", e.target.value || undefined)}>
              <option value="">Any</option><option value="left">Left</option><option value="right">Right</option>
            </select>
          </label>
          <label className="block"><span className={lbl}>Batting position</span>
            <select className={field} value={f.batting_position ?? ""} onChange={(e) => set("batting_position", e.target.value || undefined)}>
              <option value="">Any</option>
              {Array.from({ length: 11 }, (_, i) => <option key={i + 1}>{i + 1}</option>)}
            </select>
          </label>
        </div>

        <label className="block"><span className={lbl}>Split by</span>
          <select className={field} value={f.group_by} onChange={(e) => set("group_by", e.target.value)}>
            {Object.entries(GROUP_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>

        <button disabled={busy} className="w-full bg-accent text-accent-ink py-2.5 font-semibold disabled:opacity-60 focus-ring">
          {busy ? "Running…" : "Run"}
        </button>
        {error && <p className="text-sm text-bad" role="alert">{error}</p>}
      </form>

      <section className="min-w-0">
        {result ? <AnswerCard key={result.id} answer={result} /> : (
          <div className="border border-dashed border-rule p-8 text-muted text-sm">
            Pick a player and filters, then Run. Leave the player empty for all batters or bowlers, e.g. every left-hander against left-arm wrist spin.
          </div>
        )}
      </section>
    </div>
  );
}

function PlayerPicker({ value, onChange, gender }: { value: PlayerHit | null; onChange: (p: PlayerHit | null) => void; gender?: string }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<PlayerHit[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const searching = q.trim().length >= 2;
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (!searching) return;
    timer.current = setTimeout(() => api.players(q, gender).then((r) => setHits(r.candidates)).catch(() => setHits([])), 200);
  }, [q, gender, searching]);
  const shown = searching ? hits : [];

  if (value) {
    return (
      <div>
        <span className={lbl}>Player</span>
        <div className="flex items-center justify-between border border-accent bg-accent-soft px-3 py-2">
          <span><strong>{value.full_name ?? value.name}</strong> <span className="text-muted text-sm">{value.country} · {value.gender === "male" ? "men" : "women"}</span></span>
          <button type="button" onClick={() => onChange(null)} className="text-sm text-muted hover:text-ink focus-ring" aria-label="Clear player">✕</button>
        </div>
      </div>
    );
  }
  return (
    <div className="relative">
      <label className="block"><span className={lbl}>Player</span>
        <input className={field} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Any player, or search e.g. Mandhana" />
      </label>
      {shown.length > 0 && (
        <ul className="absolute z-10 left-0 right-0 bg-surface border border-rule shadow-sm max-h-72 overflow-auto">
          {shown.map((h) => (
            <li key={h.player_id}>
              <button type="button" onClick={() => { onChange(h); setQ(""); setHits([]); }}
                      className="w-full text-left px-3 py-2 hover:bg-accent-soft focus-ring">
                <span className="font-semibold">{h.full_name ?? h.name}</span>
                <span className="text-muted text-sm"> · {h.country} · {h.gender === "male" ? "men" : "women"} · {h.matches} T20Is ({h.first_match.slice(0, 4)}-{h.last_match.slice(0, 4)})</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
