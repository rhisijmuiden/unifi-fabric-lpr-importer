import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowRight, GitBranch, KeyRound, Mail, Package } from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import { api } from "@/lib/api";
import { channelLabel } from "@/lib/utils";
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

export function DashboardPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const { data: info } = useSystemInfo();
  const isAdmin = me?.role === "admin";
  const sso = useQuery({ queryKey: ["settings", "sso"], queryFn: () => api<{ enabled: boolean }>("/settings/sso"), enabled: isAdmin });
  const smtp = useQuery({ queryKey: ["settings", "smtp"], queryFn: () => api<{ host: string }>("/settings/smtp"), enabled: isAdmin });
  const next = t("dashboard.nextItems", { returnObjects: true }) as string[];

  return (
    <>
      <PageHeader title={t("dashboard.welcome", { name: me?.display_name || me?.username })} description={t("dashboard.intro")} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Package} label={t("dashboard.version")} value={<span className="font-mono">{info?.version ?? "…"}</span>} />
        <Stat
          icon={GitBranch}
          label={t("dashboard.channel")}
          value={info ? channelLabel(info.channel, t) : "…"}
          to={isAdmin ? "/admin/system" : undefined}
        />
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
      </div>
      <Card className="mt-6">
        <CardHeader title={t("dashboard.nextUp")} />
        <CardBody>
          <ul className="grid gap-3 sm:grid-cols-2">
            {next.map((item) => (
              <li key={item} className="flex items-start gap-3 text-sm">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-koraal" />
                {item}
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </>
  );
}
