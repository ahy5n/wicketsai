"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, type Me } from "@/lib/api";

type Session = Me & { loading: boolean; refresh: () => Promise<void>; setQuestionsLeft: (n: number | null | undefined) => void };

const Ctx = createContext<Session>({ user: null, loading: true, refresh: async () => {}, setQuestionsLeft: () => {} });

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me>({ user: null });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      setMe({ user: null });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial load: state is set in the promise callbacks, not synchronously in the effect.
    api.me()
      .then(setMe)
      .catch(() => setMe({ user: null }))
      .finally(() => setLoading(false));
  }, []);

  const setQuestionsLeft = useCallback((n: number | null | undefined) => {
    if (n !== undefined) setMe((m) => ({ ...m, questions_left: n }));
  }, []);

  return <Ctx.Provider value={{ ...me, loading, refresh, setQuestionsLeft }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
