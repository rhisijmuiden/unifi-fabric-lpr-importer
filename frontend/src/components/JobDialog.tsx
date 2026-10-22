import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { api, type Job } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Alert, Dialog } from "@/components/ui/misc";

/** Follows a background job until it finishes and shows its report. */
export function JobDialog({ jobId, onClose, onFinished }: { jobId: number | null; onClose: () => void; onFinished?: (job: Job) => void }) {
  const { t } = useTranslation();
  const [onlyFailed, setOnlyFailed] = useState(false);
  const { data: job } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled: jobId !== null,
    refetchInterval: (q) => (q.state.data && ["done", "failed"].includes(q.state.data.status) ? false : 1000),
  });
  const finished = job && (job.status === "done" || job.status === "failed");

  useEffect(() => {
    if (finished && job) onFinished?.(job);
  }, [finished]); // eslint-disable-line react-hooks/exhaustive-deps

  const pct = job && job.total ? Math.round((job.processed / job.total) * 100) : finished ? 100 : 0;
  const log = (job?.log ?? []).filter((e) => !onlyFailed || !e.ok);

  return (
    <Dialog open={jobId !== null} onClose={onClose} title={job ? t(`jobs.kinds.${job.kind}`) : t("common.loading")} wide>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          {!finished && <Loader2 className="h-5 w-5 animate-spin text-muted" />}
          {finished && job.status === "done" && !job.failed && <CheckCircle2 className="h-5 w-5 text-online" />}
          {finished && (job.status === "failed" || job.failed > 0) && <XCircle className="h-5 w-5 text-offline" />}
          <div className="flex-1 text-sm font-semibold">{job ? t(`jobs.status.${job.status}`) : t("common.loading")}</div>
          {job && (
            <div className="text-sm text-muted">
              {t("jobs.progress", { processed: job.processed, total: job.total })}
            </div>
          )}
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-surface ring-1 ring-line">
          <div className={cn("h-full rounded-full transition-all", job?.failed ? "bg-warning" : "bg-primary")} style={{ width: `${pct}%` }} />
        </div>
        {job && (
          <div className="grid grid-cols-3 gap-3 text-center text-sm">
            <div className="rounded-md bg-surface p-3">
              <div className="text-xl font-bold">{job.processed}</div>
              <div className="text-xs text-muted">{t("jobs.processed")}</div>
            </div>
            <div className="rounded-md bg-surface p-3">
              <div className="text-xl font-bold text-online">{job.succeeded}</div>
              <div className="text-xs text-muted">{t("jobs.succeeded")}</div>
            </div>
            <div className="rounded-md bg-surface p-3">
              <div className={cn("text-xl font-bold", job.failed ? "text-offline" : "")}>{job.failed}</div>
              <div className="text-xs text-muted">{t("jobs.failed")}</div>
            </div>
          </div>
        )}
        {job?.status === "failed" && <Alert tone="danger">{t("jobs.crashed")}</Alert>}
        {!!job?.log?.length && (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold">{t("jobs.report")}</span>
              <label className="flex items-center gap-2 text-xs text-muted">
                <input type="checkbox" checked={onlyFailed} onChange={(e) => setOnlyFailed(e.target.checked)} />
                {t("jobs.onlyFailed")}
              </label>
            </div>
            <ul className="max-h-64 space-y-1 overflow-y-auto rounded-md border border-line bg-surface p-2 font-mono text-xs">
              {log.map((e, i) => (
                <li key={i} className="flex gap-2">
                  <span className={e.ok ? "text-online" : "text-offline"}>{e.ok ? "✓" : "✕"}</span>
                  <span className="break-all">{e.message}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex justify-end">
          <Button variant={finished ? "primary" : "outline"} onClick={onClose}>
            {finished ? t("common.close") : t("jobs.background")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
