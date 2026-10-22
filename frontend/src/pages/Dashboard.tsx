import { useState, type ComponentType, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  DatabaseBackup,
  Download,
  GitBranch,
  KeyRound,
  Mail,
  Package,
  Server,
  Truck,
  XCircle,
} from "lucide-react";
import { api, type Dashboard, type DashboardLocation, type LocationStatus } from "@/lib/api";
import { channelLabel, cn, formatDate } from "@/lib/utils";
import { useMe } from "@/lib/auth";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, PageHeader } from "@/components/ui/misc";
import { JobDialog } from "@/components/JobDialog";
import { useSystemInfo } from "@/lib/system";

function Stat({ icon: Icon, label, value, to }: { icon: ComponentType<{ className?: string }>; label: string; value: ReactNode; to?: string }) {
  const body = (
    <Card className="group h-full p-5 transition-shadow hover:shadow-md">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-lucht/20 text-nacht dark:text-lucht">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm text-muted">{label}</div>
          <div className="mt-0.5 truncate font-semibold">{value}</div>
        </div>
        {to && <ArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-ink" />}
      </div>
    </Card>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

function SystemRow({ icon: Icon, label, value, to }: { icon: ComponentType<{ className?: string }>; label: string; value: ReactNode; to?: string }) {
  const body = (
    <div className="group flex items-center gap-3 py-2.5 text-sm">
      <Icon className="h-4 w-4 shrink-0 text-muted" />
      <span className="flex-1 text-muted">{label}</span>
      <span className="min-w-0 truncate text-right font-semibold">{value}</span>
      {to && <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-ink" />}
    </div>
  );
  return to ? <Link to={to} className="block">{body}</Link> : body;
}

const STATUS: Record<LocationStatus, { icon: ComponentType<{ className?: string }>; tone: "success" | "warning" | "danger" | "neutral"; ring: string }> = {
  ok: { icon: CheckCircle2, tone: "success", ring: "border-l-online" },
  warning: { icon: AlertTriangle, tone: "warning", ring: "border-l-warning" },
  error: { icon: XCircle, tone: "danger", ring: "border-l-offline" },
  unknown: { icon: CircleDashed, tone: "neutral", ring: "border-l-line" },
  inactive: { icon: CircleSlash, tone: "neutral", ring: "border-l-line" },
};

function LocationCard({ loc }: { loc: DashboardLocation }) {
  const { t, i18n } = useTranslation();
  const s = STATUS[loc.status];
  const total = loc.present + loc.missing;
  const pct = total ? Math.round((loc.present / total) * 100) : 0;
  return (
    <Card className={cn("border-l-4 p-5", s.ring)}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="truncate font-bold">{loc.name}</div>
          {loc.location && loc.location !== loc.name && <div className="truncate text-xs text-muted">{loc.location}</div>}
        </div>
        <Badge tone={s.tone}>
          <s.icon className="h-3.5 w-3.5" />
          {t(`dashboard.status.${loc.status}`)}
        </Badge>
      </div>
      <div className="mt-4">
        <div className="flex items-baseline justify-between text-sm">
          <span className="font-semibold">{t("dashboard.coverage", { present: loc.present, total })}</span>
          <span className="text-xs text-muted">{pct}%</span>
        </div>
        <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface">
          <div className={cn("h-full rounded-full", loc.missing ? "bg-warning" : "bg-online")} style={{ width: `${pct}%` }} />
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div>
          <dt className="text-muted">{t("dashboard.missingShort")}</dt>
          <dd className={cn("font-semibold", loc.missing && "text-warning")}>{loc.missing}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("dashboard.unmanagedShort")}</dt>
          <dd className="font-semibold">{loc.unmanaged}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("dashboard.lastScan")}</dt>
          <dd className="font-semibold">{loc.last_scan_at ? formatDate(loc.last_scan_at, i18n.language) : t("common.never")}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("dashboard.lastChange")}</dt>
          <dd className="font-semibold">{loc.last_change_at ? formatDate(loc.last_change_at, i18n.language) : "–"}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("dashboard.changes7d")}</dt>
          <dd className="font-semibold">{loc.changes_7d}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("dashboard.failures24h")}</dt>
          <dd className={cn("font-semibold", loc.failures_24h && "text-offline")}>{loc.failures_24h}</dd>
        </div>
      </dl>
      {(loc.scan_error || (loc.failures_24h > 0 && loc.last_failure)) && (
        <div className="mt-3 rounded-md bg-offline/10 px-3 py-2 text-xs text-ink">
          <span className="font-semibold">{t("dashboard.lastError")}: </span>
          <span className="break-words">{loc.scan_error || loc.last_failure}</span>
        </div>
      )}
      {loc.reachable === false && !loc.scan_error && <div className="mt-3 rounded-md bg-offline/10 px-3 py-2 text-xs">{t("dashboard.unreachable")}</div>}
    </Card>
  );
}

const JOB_TONE = { queued: "neutral", running: "brand", done: "success", failed: "danger" } as const;

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const { data: me } = useMe();
  const { data: info } = useSystemInfo();
  const isAdmin = me?.role === "admin";
  const [jobId, setJobId] = useState<number | null>(null);
  const sso = useQuery({ queryKey: ["settings", "sso"], queryFn: () => api<{ enabled: boolean }>("/settings/sso"), enabled: isAdmin });
  const smtp = useQuery({ queryKey: ["settings", "smtp"], queryFn: () => api<{ host: string }>("/settings/smtp"), enabled: isAdmin });
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard"), refetchInterval: 30000 });
  const d = dash.data;
  const active = d?.locations.filter((l) => l.is_active) ?? [];
  const healthy = active.filter((l) => l.status === "ok").length;
  const missing = active.reduce((n, l) => n + l.missing, 0);
  const unmanaged = d?.locations.reduce((n, l) => n + l.unmanaged, 0) ?? 0;

  const sourceOf = (s: Dashboard["syncs"][number]) => {
    if (s.schedule) return s.schedule;
    if (s.source) return t(`dashboard.sources.${s.source}`, { defaultValue: s.source });
    return s.actor_type === "system" ? t("dashboard.sources.system") : "";
  };

  return (
    <>
      <PageHeader title={t("dashboard.welcome", { name: me?.display_name || me?.username })} description={t("dashboard.intro")} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Truck} label={t("dashboard.vehicles")} value={d?.vehicles ?? "…"} to="/vehicles" />
        <Stat icon={Server} label={t("dashboard.locationsHealthy")} value={d ? t("dashboard.consolesValue", { ok: healthy, total: active.length }) : "…"} to="/consoles" />
        <Stat
          icon={AlertTriangle}
          label={t("dashboard.missing")}
          value={d ? missing ? <Badge tone="warning">{missing}</Badge> : <Badge tone="success">0</Badge> : "…"}
          to="/vehicles"
        />
        <Stat icon={Download} label={t("dashboard.unmanaged")} value={d ? unmanaged : "…"} to="/vehicles" />
      </div>

      {d && !d.locations.length && (
        <Card className="mt-6">
          <CardBody className="flex flex-wrap items-center gap-4">
            <div className="flex-1">
              <div className="font-semibold">{t("dashboard.startTitle")}</div>
              <div className="text-sm text-muted">{t("dashboard.startBody")}</div>
            </div>
            <Link to="/consoles" className="inline-flex h-10 items-center gap-2 rounded-md bg-koraal px-4 text-sm font-semibold text-nacht">
              {t("consoles.add")}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </CardBody>
        </Card>
      )}

      {!!d?.locations.length && (
        <>
          <h2 className="mb-3 mt-8 text-sm font-bold uppercase tracking-wider text-muted">{t("dashboard.perLocation")}</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {d.locations.map((loc) => (
              <LocationCard key={loc.id} loc={loc} />
            ))}
          </div>
        </>
      )}

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader title={t("dashboard.recentSyncs")} description={t("dashboard.recentSyncsHint")} />
          <CardBody>
            {d && !d.syncs.length && <p className="text-sm text-muted">{t("dashboard.noJobs")}</p>}
            <ul className="divide-y divide-line">
              {d?.syncs.map((j) => (
                <li key={j.id}>
                  <button className="flex w-full items-center gap-3 py-2.5 text-left text-sm hover:bg-surface/60" onClick={() => setJobId(j.id)}>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 font-semibold">
                        {t(`jobs.kinds.${j.kind}`)}
                        {sourceOf(j) && <span className="text-xs font-normal text-muted">· {sourceOf(j)}</span>}
                        {j.mode === "full" && <Badge tone="warning">{t("import.modes.full")}</Badge>}
                      </div>
                      <div className="truncate text-xs text-muted">
                        {j.actor} · {formatDate(j.created_at, i18n.language)}
                      </div>
                    </div>
                    <span className="text-xs text-muted">{t("jobs.progress", { processed: j.processed, total: j.total })}</span>
                    <Badge tone={j.failed && j.status === "done" ? "warning" : JOB_TONE[j.status]}>{t(`jobs.status.${j.status}`)}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader
              title={t("dashboard.schedules")}
              action={
                <Link to="/import/schedules" className="text-xs font-semibold text-muted hover:text-ink">
                  {t("dashboard.manage")}
                </Link>
              }
            />
            <CardBody>
              {d && !d.schedules.length && <p className="text-sm text-muted">{t("dashboard.noSchedules")}</p>}
              <ul className="space-y-3">
                {d?.schedules.map((s) => (
                  <li key={s.id} className="flex items-start gap-3 text-sm">
                    <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold">{s.name}</div>
                      <div className="text-xs text-muted">
                        {s.is_enabled && s.next_run ? t("dashboard.nextRun", { date: formatDate(s.next_run, i18n.language) }) : t("schedules.notScheduled")}
                      </div>
                    </div>
                    {s.last_status && <Badge tone={s.last_status === "ok" ? "success" : s.last_status === "failed" ? "danger" : "neutral"}>{t(`schedules.status.${s.last_status}`)}</Badge>}
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title={t("dashboard.system")} />
            <CardBody className="divide-y divide-line py-2">
              <SystemRow icon={Package} label={t("dashboard.version")} value={<span className="font-mono">{info?.version ?? "…"}</span>} />
              <SystemRow icon={GitBranch} label={t("dashboard.channel")} value={info ? channelLabel(info.channel, t) : "…"} to={isAdmin ? "/admin/system" : undefined} />
              <SystemRow
                icon={DatabaseBackup}
                label={t("dashboard.backup")}
                value={
                  !d ? "…" : !d.backup.targets ? (
                    <Badge tone="warning">{t("dashboard.notConfigured")}</Badge>
                  ) : d.backup.failed ? (
                    <Badge tone="danger">{t("dashboard.backupFailed", { count: d.backup.failed })}</Badge>
                  ) : d.backup.last_backup_at ? (
                    formatDate(d.backup.last_backup_at, i18n.language)
                  ) : (
                    t("common.never")
                  )
                }
                to={isAdmin ? "/admin/backup" : undefined}
              />
              {isAdmin && (
                <>
                  <SystemRow
                    icon={KeyRound}
                    label={t("dashboard.sso")}
                    value={sso.data ? <Badge tone={sso.data.enabled ? "success" : "neutral"}>{sso.data.enabled ? t("dashboard.on") : t("dashboard.off")}</Badge> : "…"}
                    to="/admin/sso"
                  />
                  <SystemRow
                    icon={Mail}
                    label={t("dashboard.mail")}
                    value={smtp.data ? smtp.data.host ? smtp.data.host : <Badge tone="warning">{t("dashboard.notConfigured")}</Badge> : "…"}
                    to="/admin/mail"
                  />
                </>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
      <JobDialog jobId={jobId} onClose={() => setJobId(null)} />
    </>
  );
}
