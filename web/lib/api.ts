// Typed client for the Python API (proxied at /api by next.config.ts).

export type Table = { columns: string[]; rows: (string | number | null)[][]; truncated?: boolean };

export type EvidenceMatch = { match_id: number; date: string; fixture: string; event: string | null; url: string };

export type Evidence = {
  match_count: number;
  balls: number | null;
  matches: EvidenceMatch[];
  first_date: string | null;
  last_date: string | null;
};

export type Answer = {
  id: string;
  thread_id?: string | null;
  question: string;
  can_answer: boolean;
  answer: string;
  display: "sentence" | "table" | "bar" | "line";
  table: Table | null;
  sql: string | null;
  evidence: Evidence | null;
  assumptions: string[];
  coverage_notes: string[];
  error: string | null;
  filters?: Record<string, unknown> | null;
  cost_usd: number;
  attribution: string;
  questions_left?: number | null;
  created_at?: string;
};

export type User = { id: number; email: string; is_admin: number; plan: string; created_at: string };

export type Me = { user: User | null; questions_left?: number | null; free_daily?: number };

export type Story = { kind: string; headline: string; detail: string; sql: string; match_id?: number };

export type Stories = { stat_of_the_day: Story[]; milestones: Story[]; streaks: Story[] };

export type Meta = {
  teams: string[];
  venues: { id: number; name: string; city: string | null }[];
  phases: string[];
  bowling_kinds: string[];
  bowling_types: string[];
  group_by: string[];
  latest_match: string;
  attribution: string;
};

export type PlayerHit = {
  player_id: string;
  name: string;
  full_name: string | null;
  country: string;
  gender: string;
  matches: number;
  first_match: string;
  last_match: string;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  me: () => call<Me>("/me"),
  signup: (email: string, password: string) => post<Me>("/auth/signup", { email, password }),
  login: (email: string, password: string) => post<Me>("/auth/login", { email, password }),
  logout: () => post<{ ok: boolean }>("/auth/logout"),
  ask: (question: string, thread_id?: string | null) => post<Answer>("/ask", { question, thread_id }),
  query: (filters: Record<string, unknown>) => post<Answer>("/query", filters),
  answer: (id: string) => call<Answer>(`/answers/${id}`),
  shared: (token: string) => call<Answer>(`/share/${token}`),
  history: () => call<{ items: { id: string; thread_id: string | null; kind: string; question: string; can_answer: number; created_at: string }[] }>("/history"),
  save: (id: string, title: string, list_name: string) => post<{ ok: boolean }>(`/answers/${id}/save`, { title, list_name }),
  unsave: (id: string) => call<{ ok: boolean }>(`/answers/${id}/save`, { method: "DELETE" }),
  saved: () => call<{ items: { answer_id: string; title: string; list_name: string; created_at: string; question: string }[] }>("/saved"),
  share: (id: string) => post<{ token: string }>(`/answers/${id}/share`),
  report: (id: string, comment: string) => post<{ ok: boolean }>(`/answers/${id}/report`, { comment }),
  players: (q: string, gender?: string) =>
    call<{ candidates: PlayerHit[] }>(`/players?q=${encodeURIComponent(q)}${gender ? `&gender=${gender}` : ""}`),
  meta: () => call<Meta>("/meta"),
  stories: () => call<Stories>("/stories"),
  admin: () => call<AdminStats>("/admin"),
  setReport: (id: number, status: "open" | "resolved" | "wontfix") => post<{ ok: boolean }>(`/admin/reports/${id}`, { status }),
};

export type AdminStats = {
  totals: { questions: number; answered: number | null; usd: number | null; active_users: number; avg_seconds: number | null };
  per_day: { day: string; questions: number; usd: number }[];
  popular: { question: string; n: number }[];
  cant_answer: { id: string; question: string; error: string | null; created_at: string }[];
  reports: { id: number; answer_id: string; comment: string; status: string; created_at: string; email: string | null; question: string }[];
  users: { id: number; email: string; plan: string; is_admin: number; created_at: string; questions: number }[];
};
