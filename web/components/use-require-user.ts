"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useSession } from "./session";

/** Sends signed-out visitors to /login; returns the session. */
export function useRequireUser() {
  const session = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!session.loading && !session.user) router.replace("/login");
  }, [session.loading, session.user, router]);
  return session;
}
