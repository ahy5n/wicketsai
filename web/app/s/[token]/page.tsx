"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Answer } from "@/lib/api";
import { AnswerCard } from "@/components/answer-card";

/** Public, read-only view of a shared answer. No account needed. */
export default function SharedPage() {
  const { token } = useParams<{ token: string }>();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    api.shared(token).then(setAnswer).catch(() => setMissing(true));
  }, [token]);

  return (
    <div className="max-w-3xl">
      {missing && <p className="text-muted">This link doesn&apos;t exist or has been removed.</p>}
      {answer && (
        <>
          <AnswerCard answer={answer} owned={false} />
          <p className="mt-4 text-sm text-muted">
            Shared from Wickets.ai{answer.created_at ? `, ${new Date(answer.created_at).toLocaleDateString("en-GB")}` : ""}.{" "}
            <Link href="/login" className="text-accent font-semibold">Ask your own question</Link>
          </p>
        </>
      )}
    </div>
  );
}
