"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, type Answer, type Stories } from "@/lib/api";
import { AnswerCard } from "@/components/answer-card";
import { AskBox, Thinking } from "@/components/ask-box";
import { useRequireUser } from "@/components/use-require-user";

const EXAMPLES = [
  "How many sixes has Suryakumar Yadav hit off spinners in T20Is?",
  "Bumrah vs Shaheen Afridi at the death: economy, dot-ball % and wickets.",
  "Highest powerplay totals in women's T20Is since 2020",
  "How has Phil Salt's strike rate changed year by year?",
  "Left-handed batters' strike rate against left-arm wrist spin",
  "When did a No. 11 last top-score in a men's T20I?",
];

export default function AskPage() {
  const { user, loading, questions_left, setQuestionsLeft } = useRequireUser();
  const [thread, setThread] = useState<Answer[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stories, setStories] = useState<Stories | null>(null);

  useEffect(() => {
    if (user) api.stories().then(setStories).catch(() => setStories(null));
  }, [user]);

  async function ask(q: string) {
    setPending(q);
    setError(null);
    try {
      const a = await api.ask(q, thread.at(-1)?.thread_id ?? null);
      setThread((t) => [...t, a]);
      setQuestionsLeft(a.questions_left);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The question couldn't be answered. Try again.");
    } finally {
      setPending(null);
    }
  }

  if (loading || !user) return null;
  const outOfQuestions = questions_left === 0;

  return (
    <div className="grid lg:grid-cols-[1fr_17rem] gap-10">
      <section className="min-w-0">
        {thread.length === 0 && !pending && (
          <h1 className="font-serif text-3xl sm:text-4xl font-bold leading-tight mb-5">What do you need to know?</h1>
        )}

        <div className="space-y-6">
          {thread.map((a) => <AnswerCard key={a.id} answer={a} />)}
          {pending && <Thinking question={pending} />}
        </div>

        <div className={thread.length || pending ? "mt-6" : ""}>
          {error && <p className="mb-3 text-bad text-sm" role="alert">{error}</p>}
          {outOfQuestions ? (
            <p className="bg-accent-soft p-4 text-sm">
              You&apos;ve used today&apos;s free questions. <Link href="/filters" className="text-accent font-semibold underline">Filters</Link> and
              story prompts stay unlimited.
            </p>
          ) : (
            <AskBox
              onAsk={ask}
              busy={!!pending}
              autoFocus
              placeholder={thread.length ? "Follow up: “now only away games”, “and since 2022?”" : "Ask about any T20I player, team or record"}
            />
          )}
          {thread.length > 0 && !pending && (
            <button onClick={() => setThread([])} className="mt-3 text-sm text-muted hover:text-ink focus-ring">Start a new question</button>
          )}
        </div>

        {thread.length === 0 && !pending && (
          <div className="mt-8">
            <p className="text-xs uppercase tracking-wider text-muted mb-3">Try</p>
            <ul className="divide-y divide-rule border-y border-rule">
              {EXAMPLES.map((q) => (
                <li key={q}>
                  <button onClick={() => ask(q)} disabled={outOfQuestions}
                          className="w-full text-left py-3 hover:text-accent disabled:opacity-50 focus-ring">{q}</button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <aside className="lg:border-l lg:border-rule lg:pl-8">
        <h2 className="text-xs uppercase tracking-wider text-muted mb-4">Story prompts</h2>
        {!stories ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : (
          <div className="space-y-6 text-sm">
            <StoryList title="On this day" items={stories.stat_of_the_day} />
            <StoryList title="Milestones within reach" items={stories.milestones.slice(0, 6)} />
            <StoryList title="Streaks" items={stories.streaks.slice(0, 5)} />
          </div>
        )}
      </aside>
    </div>
  );
}

function StoryList({ title, items }: { title: string; items: Stories["milestones"] }) {
  if (!items.length) return null;
  return (
    <div>
      <h3 className="font-serif font-bold text-base mb-2">{title}</h3>
      <ul className="space-y-3">
        {items.map((s) => (
          <li key={s.headline}>
            <p className="leading-snug">{s.headline}</p>
            <p className="text-muted text-xs mt-0.5">{s.detail}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
