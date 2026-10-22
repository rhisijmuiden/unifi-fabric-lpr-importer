export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

export async function api<T = unknown>(path: string, options: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const json = options.body !== undefined;
  const res = await fetch(`/api${path}`, {
    method: options.method ?? (options.form ? "POST" : "GET"),
    credentials: "same-origin",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(json ? { "Content-Type": "application/json" } : {}),
    },
    body: options.form ?? (json ? JSON.stringify(options.body) : undefined),
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

export interface Console {
  id: number;
  name: string;
  location: string;
  host: string;
  port: number;
  verify_tls: boolean;
  is_active: boolean;
  sort_order: number;
  api_token_set: boolean;
  last_test_at: string | null;
  last_test_ok: boolean | null;
  last_test_message: string;
  last_scan_at: string | null;
  plates: number;
}

export interface ConsoleTestResult {
  ok: boolean;
  users?: number;
  groups?: number;
  code?: string;
  message?: string;
}

export interface Presence {
  user: string;
  groups: string[];
  seen_at: string | null;
}

export interface Vehicle {
  id: number;
  plate: string;
  plate_key: string;
  department: string;
  location: string;
  group_name: string;
  description: string;
  source: "manual" | "csv" | "api" | "console";
  created_at: string;
  updated_at: string;
  presence: Record<string, Presence>;
}

export interface VehicleList {
  consoles: { id: number; name: string; location: string; is_active: boolean; last_scan_at: string | null }[];
  items: Vehicle[];
}

export interface AdoptCandidate {
  plate_key: string;
  plate: string;
  department: string;
  location: string;
  group_name: string;
  user_name: string;
  follows_convention: boolean;
  consoles: string[];
}

export interface JobLogEntry {
  at: string;
  ok: boolean;
  message: string;
  console?: string;
  plate?: string;
  code?: string;
}

export interface Job {
  id: number;
  kind: "scan" | "assign" | "remove" | "import" | "backup" | "restore";
  status: "queued" | "running" | "done" | "failed";
  actor_type: string;
  actor: string;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  result: Record<string, unknown> | null;
  created_at: string;
  finished_at: string | null;
  log?: JobLogEntry[];
}

export type ImportField = "plate" | "department" | "location" | "group_name" | "description";

export interface ImportRow {
  plate: string;
  department: string;
  location: string;
  group_name: string;
  description: string;
}

export interface PlannedRow extends ImportRow {
  row: number;
  plate_key: string;
  status: "new" | "changed" | "unchanged" | "invalid";
  error: string | null;
}

export interface ImportPlan {
  rows: PlannedRow[];
  summary: { total: number; new: number; changed: number; unchanged: number; invalid: number; remove: number; groups: string[] };
  remove: string[];
  consoles: { id: number; name: string; add: number; present: number; remove: number; selected: boolean; scanned_at: string | null }[];
}

export interface Stats {
  vehicles: number;
  departments: { name: string; count: number }[];
  locations: { name: string; count: number }[];
  groups: { name: string; count: number }[];
  sources: { name: string; count: number }[];
  consoles: { id: number; name: string; location: string; is_active: boolean; present: number; missing: number; unmanaged: number; last_scan_at: string | null }[];
  activity: { day: string; added: number; removed: number }[];
  totals_30d: { added: number; removed: number };
}

export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  allow_delete: boolean;
  allowed_ips: string[];
  is_active: boolean;
  created_by: string;
  created_at: string;
  last_used_at: string | null;
}

export interface BackupTarget {
  id: number;
  name: string;
  protocol: "ftp" | "ftps" | "scp";
  host: string;
  port: number;
  username: string;
  password_set: boolean;
  auth_method: "password" | "key";
  host_key: string;
  remote_path: string;
  ftps_implicit: boolean;
  verify_tls: boolean;
  passive: boolean;
  is_enabled: boolean;
  last_backup_at: string | null;
  last_backup_name: string;
  last_status: "" | "ok" | "failed";
  last_message: string;
}

export interface BackupTestResult {
  ok: boolean;
  host_key?: string;
  backups?: number;
  code?: string | null;
  message?: string;
}

export interface BackupSchedule {
  enabled: boolean;
  frequency: "hourly" | "daily" | "weekly" | "monthly";
  time: string;
  weekday: number;
  monthday: number;
}

export interface BackupSettings {
  passphrase_set: boolean;
  keep_full: number;
  schedule_full: BackupSchedule;
  schedule_incremental: BackupSchedule;
  notify_email: string;
  notify_on: "failure" | "always" | "never";
  ssh_public_key: string;
  next_runs: { full: string | null; incremental: string | null };
}

export interface BackupItem {
  name: string;
  kind: "full" | "incremental";
  created_at: string;
  parent: string | null;
  size: number | null;
  restorable: boolean;
  chain_length: number;
}
