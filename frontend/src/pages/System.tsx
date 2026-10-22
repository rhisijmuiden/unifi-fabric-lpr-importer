import { useTranslation } from "react-i18next";
import { channelLabel, formatDate } from "@/lib/utils";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/misc";
import { useSystemInfo } from "@/lib/system";
import { UpdatePanel } from "@/components/UpdatePanel";

function duration(seconds: number) {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
}

export function SystemPage() {
  const { t, i18n } = useTranslation();
  const { data: info } = useSystemInfo();
  const rows: [string, string][] = info
    ? [
        [t("system.version"), info.version],
        [t("system.channel"), channelLabel(info.channel, t)],
        [t("system.commit"), info.commit ?? "–"],
        [t("system.released"), formatDate(info.commit_date, i18n.language)],
        [t("system.uptime"), duration(info.uptime_seconds)],
        ["Python", info.python],
      ]
    : [];
  return (
    <>
      <PageHeader title={t("system.title")} description={t("system.description")} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title={t("system.installed")} />
          <CardBody>
            <dl className="space-y-3 text-sm">
              {rows.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-mono text-right">{v}</dd>
                </div>
              ))}
            </dl>
          </CardBody>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title={t("system.channels")} />
          <CardBody>
            <UpdatePanel />
          </CardBody>
        </Card>
      </div>
    </>
  );
}
