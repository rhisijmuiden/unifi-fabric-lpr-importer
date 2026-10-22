export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

export async function api<T = unknown>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: options.method ?? "GET",
    credentials: "same-origin",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : res.statusText;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export type Role = "admin" | "operator" | "viewer";

export interface User {
  id: number;
  username: string;
  display_name: string;
  email: string;
  role: Role;
  auth_source: "local" | "entra";
  language: "en" | "nl";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface SystemInfo {
  version: string;
  channel: string | null;
  commit: string | null;
  commit_date: string | null;
  python: string;
  uptime_seconds: number;
}

export interface ChannelInfo {
  version: string;
  commit: string;
  commit_date: string;
  is_current: boolean;
  update_available: boolean;
}

export interface UpdateCheck {
  current: SystemInfo;
  channels: Record<string, ChannelInfo>;
  checked_at: string;
}

export interface UpdateStatus {
  state: "idle" | "running" | "success" | "failed";
  message?: string;
  channel?: string;
  updated_at?: string;
  log: string[];
}

export interface AuditEntry {
  id: number;
  created_at: string;
  actor_type: string;
  actor: string;
  action: string;
  target: string;
  details: Record<string, unknown>;
  ip_address: string;
  success: boolean;
  message: string;
}
