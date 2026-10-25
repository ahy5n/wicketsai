"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useSession } from "@/components/session";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { refresh } = useSession();
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await (mode === "login" ? api.login(email, password) : api.signup(email, password));
      await refresh();
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-6 sm:mt-14">
      <h1 className="font-serif text-3xl font-bold leading-tight">Every T20I ball. Any question. With the receipts.</h1>
      <p className="mt-3 text-muted">
        Ask in plain English and get the number, the table and the matches behind it, ready to go into print.
      </p>

      <div className="mt-8 flex border-b border-rule text-sm">
        {(["login", "signup"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)}
                  className={`flex-1 pb-2 focus-ring ${mode === m ? "border-b-2 border-accent font-semibold" : "text-muted"}`}>
            {m === "login" ? "Sign in" : "Create account"}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="mt-5 flex flex-col gap-3">
        <label className="text-sm">
          Email
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)}
                 className="mt-1 w-full border border-rule bg-surface px-3 py-2.5 focus-ring" />
        </label>
        <label className="text-sm">
          Password {mode === "signup" && <span className="text-muted">(8+ characters)</span>}
          <input type="password" required minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"}
                 value={password} onChange={(e) => setPassword(e.target.value)}
                 className="mt-1 w-full border border-rule bg-surface px-3 py-2.5 focus-ring" />
        </label>
        {error && <p className="text-sm text-bad" role="alert">{error}</p>}
        <button disabled={busy} className="mt-2 bg-accent text-accent-ink py-2.5 font-semibold disabled:opacity-60 focus-ring">
          {busy ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        {mode === "signup" && <p className="text-xs text-muted">Free accounts get 5 questions a day. Filters and story prompts are unlimited.</p>}
      </form>
    </div>
  );
}
