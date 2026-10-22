import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Activity, Building2, Minus, Plus, Truck, Users } from "lucide-react";
import type { ComponentType } from "react";
import { api, type Stats } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/misc";

export function StatTile({ icon: Icon, label, value, hint }: { icon: ComponentType<{ className?: string }>; label: string; value: number | string; hint?: string }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div className="mt-2 font-display-wide text-3xl tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

/** Single-series horizontal bars: one hue, value label in ink beside the bar. */
function Bars({ rows, empty }: { rows: { name: string; count: number }[]; empty: string }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.name} className="grid grid-cols-[minmax(6rem,12rem)_1fr_3rem] items-center gap-3 text-sm" title={`${r.name || "–"}: ${r.count}`}>
          <span className="truncate">{r.name || "–"}</span>
          <span className="h-2.5 rounded-r bg-surface">
            <span className="block h-full rounded-r bg-primary" style={{ width: `${(r.count / max) * 100}%` }} />
          </span>
          <span className="text-right font-semibold tabular-nums">{r.count}</span>
        </li>
      ))}
    </ul>
  );
}

export function StatisticsPage() {
  const { t, i18n } = useTranslation();
  const { data } = useQuery({ queryKey: ["stats"], queryFn: () => api<Stats>("/stats") });
  const maxDay = Math.max(1, ...(data?.activity ?? []).flatMap((d) => [d.added, d.removed]));

  return (
    <>
      <PageHeader title={t("stats.title")} description={t("stats.description")} />
      {data && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile icon={Truck} label={t("stats.vehicles")} value={data.vehicles} />
            <StatTile icon={Building2} label={t("stats.departments")} value={data.departments.filter((d) => d.name).length} />
            <StatTile icon={Users} label={t("stats.groups")} value={data.groups.filter((d) => d.name).length} />
            <StatTile icon={Activity} label={t("stats.changes30d")} value={`+${data.totals_30d.added} / −${data.totals_30d.removed}`} hint={t("stats.changesHint")} />
          </div>

          <Card>
            <CardHeader title={t("stats.perConsole")} description={t("stats.perConsoleHint")} />
            <CardBody>
              {!data.consoles.length && <p className="text-sm text-muted">{t("stats.noConsoles")}</p>}
              <ul className="space-y-4">
                {data.consoles.map((c) => {
                  const total = c.present + c.missing;
                  const pct = total ? Math.round((c.present / total) * 100) : 0;
                  return (
                    <li key={c.id}>
                      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-3 text-sm">
                        <span className="font-semibold">{c.name}</span>
                        <span className="text-muted">{c.location}</span>
                        <span className="ml-auto text-muted">
                          {c.last_scan_at ? t("stats.scanned", { time: formatDate(c.last_scan_at, i18n.language) }) : t("vehicles.notScanned")}
                        </span>
                      </div>
                      <div className="flex h-3 gap-0.5 overflow-hidden rounded" title={`${c.present} / ${total}`}>
                        {c.present > 0 && <div className="rounded-l bg-online" style={{ width: `${pct}%` }} />}
                        {c.missing > 0 && <div className="flex-1 rounded-r bg-line" />}
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-x-4 text-xs text-muted">
                        <span>{t("stats.present", { count: c.present })} ({pct}%)</span>
                        <span>{t("stats.missing", { count: c.missing })}</span>
                        <span>{t("stats.unmanaged", { count: c.unmanaged })}</span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </CardBody>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title={t("stats.byDepartment")} />
              <CardBody>
                <Bars rows={data.departments} empty={t("stats.none")} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title={t("stats.byLocation")} />
              <CardBody>
                <Bars rows={data.locations} empty={t("stats.none")} />
              </CardBody>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader title={t("stats.byGroup")} />
              <CardBody>
                <Bars rows={data.groups} empty={t("stats.none")} />
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader
              title={t("stats.activity")}
              description={t("stats.activityHint")}
              action={
                <div className="flex gap-4 text-xs text-muted">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-sm bg-primary" />
                    <Plus className="h-3 w-3" />
                    {t("stats.added")}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-sm bg-koraal" />
                    <Minus className="h-3 w-3" />
                    {t("stats.removed")}
                  </span>
                </div>
              }
            />
            <CardBody>
              {!data.activity.length ? (
                <p className="text-sm text-muted">{t("stats.noActivity")}</p>
              ) : (
                <div className="flex h-40 items-end gap-2 overflow-x-auto border-b border-line pb-px">
                  {data.activity.map((d) => (
                    <div key={d.day} className="flex min-w-8 flex-1 flex-col items-center gap-1" title={`${d.day}: +${d.added} / −${d.removed}`}>
                      <div className="flex h-32 w-full items-end justify-center gap-0.5">
                        <div className="w-2.5 rounded-t bg-primary" style={{ height: `${(d.added / maxDay) * 100}%` }} />
                        <div className="w-2.5 rounded-t bg-koraal" style={{ height: `${(d.removed / maxDay) * 100}%` }} />
                      </div>
                      <div className="text-[10px] text-muted">{d.day.slice(5)}</div>
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      )}
    </>
  );
}
