"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, type Answer } from "@/lib/api";
import { AnswerCard } from "@/components/answer-card";
import { useRequireUser } from "@/components/use-require-user";

export default function AnswerPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useRequireUser();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) api.answer(id).then(setAnswer).catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load that answer."));
  }, [id, user]);

  return (
    <div className="max-w-3xl">
      <Link href="/saved" className="text-sm text-muted hover:text-ink">← Saved and recent</Link>
      <div className="mt-4">
        {error && <p className="text-bad">{error}</p>}
        {answer && <AnswerCard answer={answer} />}
        {answer?.created_at && <p className="mt-3 text-xs text-muted">Answered {new Date(answer.created_at).toLocaleString("en-GB")}</p>}
      </div>
    </div>
  );
}
