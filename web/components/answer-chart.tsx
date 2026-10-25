"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Table } from "@/lib/api";

// Counting columns make dull charts; prefer the stat the question is about.
const PREFERRED = ["runs", "wickets", "strike_rate", "economy", "average", "sixes", "total", "powerplay_runs", "death_wickets"];
const SECONDARY = new Set(["matches", "balls", "innings", "match_id", "year"]);

/** Picks the x column (first) and the most meaningful numeric column; null if the table can't be charted. */
export function chartSpec(table: Table | null) {
  if (!table || table.rows.length < 2 || table.columns.length < 2) return null;
  const numeric = table.columns
    .map((c, i) => ({ c, i }))
    .filter(({ i }) => i > 0 && table.rows.every((r) => typeof r[i] === "number" || r[i] === null));
  if (!numeric.length) return null;
  const pick =
    PREFERRED.map((p) => numeric.find(({ c }) => c === p)).find(Boolean) ??
    numeric.find(({ c }) => !SECONDARY.has(c)) ??
    numeric[0];
  return { x: table.columns[0], y: pick.c, yIdx: pick.i };
}

/** SVG presentation attributes can't use var(); resolve the theme colours to real values. */
function useThemeColors() {
  const [c, setC] = useState({ accent: "#0e7c7b", muted: "#5f5f5a", rule: "#dedbd2", ink: "#111111", surface: "#ffffff", soft: "#e3f1f0" });
  useEffect(() => {
    const read = () => {
      const s = getComputedStyle(document.documentElement);
      const v = (n: string) => s.getPropertyValue(n).trim();
      setC({ accent: v("--accent"), muted: v("--muted"), rule: v("--rule"), ink: v("--ink"), surface: v("--surface"), soft: v("--accent-soft") });
    };
    read();
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", read);
    return () => mq.removeEventListener("change", read);
  }, []);
  return c;
}

export function AnswerChart({ table, kind }: { table: Table; kind: "bar" | "line" }) {
  const col = useThemeColors();
  const spec = chartSpec(table);
  if (!spec) return null;
  const data = table.rows.slice(0, 40).map((r) => ({ x: String(r[0] ?? "-"), y: r[spec.yIdx] as number }));
  const common = { data, margin: { top: 8, right: 8, bottom: 4, left: 0 } };
  const axisStyle = { fontSize: 12, fill: col.muted };

  return (
    <figure className="my-4" aria-label={`${spec.y} by ${spec.x}`}>
      <figcaption className="text-xs uppercase tracking-wider text-muted mb-2">
        {spec.y.replaceAll("_", " ")} by {spec.x.replaceAll("_", " ")}
      </figcaption>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {kind === "line" ? (
            <LineChart {...common}>
              <CartesianGrid stroke={col.rule} vertical={false} />
              <XAxis dataKey="x" tick={axisStyle} tickLine={false} axisLine={{ stroke: col.ink }} />
              <YAxis tick={axisStyle} tickLine={false} axisLine={false} width={44} />
              <Tooltip contentStyle={{ background: col.surface, border: `1px solid ${col.rule}`, fontSize: 13 }} />
              <Line type="monotone" dataKey="y" name={spec.y} stroke={col.accent} strokeWidth={2.5} dot={{ r: 3 }} />
            </LineChart>
          ) : (
            <BarChart {...common}>
              <CartesianGrid stroke={col.rule} vertical={false} />
              <XAxis dataKey="x" tick={axisStyle} tickLine={false} axisLine={{ stroke: col.ink }} interval={0}
                     angle={data.length > 6 ? -35 : 0} textAnchor={data.length > 6 ? "end" : "middle"} height={data.length > 6 ? 60 : 30} />
              <YAxis tick={axisStyle} tickLine={false} axisLine={false} width={44} />
              <Tooltip cursor={{ fill: col.soft }}
                       contentStyle={{ background: col.surface, border: `1px solid ${col.rule}`, fontSize: 13 }} />
              <Bar dataKey="y" name={spec.y} fill={col.accent} radius={[2, 2, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
