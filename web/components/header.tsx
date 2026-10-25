"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "./session";

export function Header() {
  const { user, questions_left, refresh } = useSession();
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const links = [
    { href: "/", label: "Ask" },
    { href: "/filters", label: "Filters" },
    { href: "/saved", label: "Saved" },
    ...(user?.is_admin ? [{ href: "/admin", label: "Admin" }] : []),
  ];

  async function logout() {
    await api.logout();
    await refresh();
    router.push("/login");
  }

  return (
    <header className="border-b border-ink/90 bg-surface">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
        <Link href="/" className="font-serif text-xl font-bold tracking-tight focus-ring">
          Wickets<span className="text-accent">.ai</span>
        </Link>

        {user && (
          <nav className="hidden sm:flex items-center gap-6 text-sm">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`focus-ring pb-0.5 ${path === l.href ? "border-b-2 border-accent font-semibold" : "text-muted hover:text-ink"}`}
              >
                {l.label}
              </Link>
            ))}
          </nav>
        )}

        <div className="flex items-center gap-3 text-sm">
          {user ? (
            <>
              {questions_left !== null && questions_left !== undefined && (
                <span className="hidden sm:inline text-muted" title="Free questions left today">
                  {questions_left} left today
                </span>
              )}
              <button onClick={logout} className="hidden sm:inline text-muted hover:text-ink focus-ring">
                Sign out
              </button>
              <button
                className="sm:hidden p-2 -mr-2 focus-ring"
                aria-label="Menu"
                aria-expanded={open}
                onClick={() => setOpen((o) => !o)}
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d={open ? "M6 6l12 12M18 6L6 18" : "M4 7h16M4 12h16M4 17h16"} />
                </svg>
              </button>
            </>
          ) : (
            path !== "/login" && (
              <Link href="/login" className="font-semibold text-accent focus-ring">
                Sign in
              </Link>
            )
          )}
        </div>
      </div>

      {user && open && (
        <nav className="sm:hidden border-t border-rule px-4 py-2 flex flex-col text-base">
          {links.map((l) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="py-3 border-b border-rule last:border-0">
              {l.label}
            </Link>
          ))}
          {questions_left !== null && questions_left !== undefined && (
            <span className="py-3 text-sm text-muted">{questions_left} free questions left today</span>
          )}
          <button onClick={logout} className="py-3 text-left text-muted">
            Sign out
          </button>
        </nav>
      )}
    </header>
  );
}
