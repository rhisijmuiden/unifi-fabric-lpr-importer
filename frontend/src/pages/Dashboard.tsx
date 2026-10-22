import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Download, GitBranch, KeyRound, Mail, Package, Server, Truck } from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import { api, type Console, type Job, type Stats } from "@/lib/api";
import { channelLabel, formatDate } from "@/lib/utils";
import { useMe } from "@/lib/auth";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, PageHeader } from "@/components/ui/misc";
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
          <div className="mt-0.5 font-semibold">{value}</div>
        </div>
        {to && <ArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-ink" />}
      </div>
    </Card>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

const JOB_TONE = { queued: "neutral", running: "brand", done: "success", failed: "danger" } as const;

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const { data: me } = useMe();
  const { data: info } = useSystemInfo();
  const isAdmin = me?.role === "admin";
  const sso = useQuery({ queryKey: ["settings", "sso"], queryFn: () => api<{ enabled: boolean }>("/settings/sso"), enabled: isAdmin });
  const smtp = useQuery({ queryKey: ["settings", "smtp"], queryFn: () => api<{ host: string }>("/settings/smtp"), enabled: isAdmin });
  const stats = useQuery({ queryKey: ["stats"], queryFn: () => api<Stats>("/stats") });
  const consoles = useQuery({ queryKey: ["consoles"], queryFn: () => api<Console[]>("/consoles") });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => api<Job[]>("/jobs?limit=6") });
  const active = consoles.data?.filter((c) => c.is_active) ?? [];
  const missing = stats.data?.consoles.filter((c) => c.is_active).reduce((n, c) => n + c.missing, 0) ?? 0;
  const unmanaged = stats.data?.consoles.reduce((n, c) => n + c.unmanaged, 0) ?? 0;

  return (
    <>
      <PageHeader title={t("dashboard.welcome", { name: me?.display_name || me?.username })} description={t("dashboard.intro")} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Truck} label={t("dashboard.vehicles")} value={stats.data?.vehicles ?? "…"} to="/vehicles" />
        <Stat
          icon={Server}
          label={t("dashboard.consoles")}
          value={consoles.data ? t("dashboard.consolesValue", { ok: active.filter((c) => c.last_test_ok).length, total: active.length }) : "…"}
          to="/consoles"
        />
        <Stat
          icon={AlertTriangle}
          label={t("dashboard.missing")}
          value={stats.data ? (missing ? <Badge tone="warning">{missing}</Badge> : <Badge tone="success">0</Badge>) : "…"}
          to="/vehicles"
        />
        <Stat icon={Download} label={t("dashboard.unmanaged")} value={stats.data ? unmanaged : "…"} to="/vehicles" />
      </div>

      {consoles.data && !consoles.data.length && (
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

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title={t("dashboard.recentJobs")} />
          <CardBody>
            {!jobs.data?.length && <p className="text-sm text-muted">{t("dashboard.noJobs")}</p>}
            <ul className="divide-y divide-line">
              {jobs.data?.map((j) => (
                <li key={j.id} className="flex items-center gap-3 py-2.5 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold">{t(`jobs.kinds.${j.kind}`)}</div>
                    <div className="truncate text-xs text-muted">
                      {j.actor} · {formatDate(j.created_at, i18n.language)}
                    </div>
                  </div>
                  <span className="text-xs text-muted">{t("jobs.progress", { processed: j.processed, total: j.total })}</span>
                  <Badge tone={j.failed && j.status === "done" ? "warning" : JOB_TONE[j.status]}>{t(`jobs.status.${j.status}`)}</Badge>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("dashboard.system")} />
          <CardBody className="grid gap-3 sm:grid-cols-2">
            <Stat icon={Package} label={t("dashboard.version")} value={<span className="font-mono">{info?.version ?? "…"}</span>} />
            <Stat icon={GitBranch} label={t("dashboard.channel")} value={info ? channelLabel(info.channel, t) : "…"} to={isAdmin ? "/admin/system" : undefined} />
            {isAdmin && (
              <>
                <Stat
                  icon={KeyRound}
                  label={t("dashboard.sso")}
                  value={sso.data ? <Badge tone={sso.data.enabled ? "success" : "neutral"}>{sso.data.enabled ? t("dashboard.on") : t("dashboard.off")}</Badge> : "…"}
                  to="/admin/sso"
                />
                <Stat
                  icon={Mail}
                  label={t("dashboard.mail")}
                  value={smtp.data ? (smtp.data.host ? <span className="truncate">{smtp.data.host}</span> : <Badge tone="warning">{t("dashboard.notConfigured")}</Badge>) : "…"}
                  to="/admin/mail"
                />
              </>
            )}
          </CardBody>
        </Card>
      </div>
    </>
  );
}
