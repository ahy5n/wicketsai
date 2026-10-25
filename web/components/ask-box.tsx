"use client";

import { useEffect, useState } from "react";

const STEPS = ["Reading the question", "Finding the players", "Writing the query", "Checking the numbers"];

export function AskBox({ onAsk, busy, placeholder, disabled, autoFocus }: {
  onAsk: (q: string) => void;
  busy: boolean;
  placeholder: string;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const [q, setQ] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim().length >= 3 && !busy) {
          onAsk(q.trim());
          setQ("");
        }
      }}
      className="flex flex-col sm:flex-row gap-2"
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
        disabled={disabled || busy}
        autoFocus={autoFocus}
        maxLength={500}
        aria-label="Your question"
        className="flex-1 border-2 border-ink bg-surface px-4 py-3 text-lg focus-ring disabled:opacity-60"
      />
      <button disabled={disabled || busy || q.trim().length < 3}
              className="bg-accent text-accent-ink px-6 py-3 text-lg font-semibold disabled:opacity-50 focus-ring">
        Ask
      </button>
    </form>
  );
}

/** Honest progress: the engine doesn't stream steps, so this shows elapsed time and a rotating hint. */
export function Thinking({ question }: { question: string }) {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setT((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="bg-surface border border-rule p-5 sm:p-7" role="status" aria-live="polite">
      <p className="text-xs uppercase tracking-wider text-muted mb-2">{question}</p>
      <p className="font-serif text-xl text-muted">
        {STEPS[Math.min(Math.floor(t / 8), STEPS.length - 1)]}…
        <span className="ml-2 text-sm font-sans tabular-nums">{t}s</span>
      </p>
      <p className="text-sm text-muted mt-2">Every figure is checked against the ball-by-ball database; most answers take 20-60 seconds.</p>
    </div>
  );
}
