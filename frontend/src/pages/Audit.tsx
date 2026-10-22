import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import { api, type AuditEntry } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Badge, PageHeader } from "@/components/ui/misc";

const PAGE = 50;

export function AuditPage() {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const { data } = useQuery({
    queryKey: ["audit", q, offset],
    queryFn: () => api<{ total: number; items: AuditEntry[] }>(`/audit?limit=${PAGE}&offset=${offset}&q=${encodeURIComponent(q)}`),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader title={t("audit.title")} description={t("audit.description")} />
      <Card className="overflow-hidden">
        <div className="border-b border-line p-4">
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input
              className="pl-9"
              placeholder={t("common.search")}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
              }}
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-xs font-medium uppercase tracking-wide text-muted">
              <tr>
                <th className="px-6 py-3">{t("audit.time")}</th>
                <th className="px-6 py-3">{t("audit.actor")}</th>
                <th className="px-6 py-3">{t("audit.action")}</th>
                <th className="px-6 py-3">{t("audit.target")}</th>
                <th className="px-6 py-3">{t("audit.result")}</th>
                <th className="px-6 py-3">{t("audit.ip")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data?.items.map((e) => (
                <tr key={e.id} className="align-top">
                  <td className="whitespace-nowrap px-6 py-3 text-muted">{formatDate(e.created_at, i18n.language)}</td>
                  <td className="px-6 py-3">
                    <div className="font-medium">{e.actor}</div>
                    <div className="text-xs text-muted">{e.actor_type}</div>
                  </td>
                  <td className="px-6 py-3 font-mono text-xs">{e.action}</td>
                  <td className="px-6 py-3">
                    {e.target}
                    {e.message && <div className="text-xs text-muted">{e.message}</div>}
                  </td>
                  <td className="px-6 py-3">
                    <Badge tone={e.success ? "success" : "danger"}>{e.success ? t("audit.ok") : t("audit.failed")}</Badge>
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-muted">{e.ip_address}</td>
                </tr>
              ))}
              {data && !data.items.length && (
                <tr>
                  <td colSpan={6} className="px-6 py-10 text-center text-muted">
                    {t("audit.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {data && data.total > PAGE && (
          <div className="flex items-center justify-between border-t border-line px-6 py-3 text-sm">
            <span className="text-muted">
              {offset + 1}–{Math.min(offset + PAGE, data.total)} / {data.total}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                {t("common.previous")}
              </Button>
              <Button variant="outline" size="sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                {t("common.next")}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
