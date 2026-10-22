import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowRightLeft, CheckCircle2, Download, Loader2, RefreshCw } from "lucide-react";
import { api, type UpdateCheck, type UpdateStatus } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { channelLabel, cn, formatDate } from "@/lib/utils";
import { useSystemInfo } from "@/lib/system";
import { Button } from "@/components/ui/button";
import { Alert, Badge } from "@/components/ui/misc";

const CHANNELS = ["main", "test"] as const;

export function UpdatePanel({ compact }: { compact?: boolean }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const wasRunning = useRef(false);
  const { data: info } = useSystemInfo();

  const status = useQuery({
    queryKey: ["update-status"],
    queryFn: () => api<UpdateStatus>("/system/update-status"),
    // Keep polling while an update runs; the API is briefly down during the restart.
    refetchInterval: (q) => (q.state.data?.state === "running" || q.state.error ? 3000 : false),
    retry: true,
  });
  const running = status.data?.state === "running";

  useEffect(() => {
    if (running) wasRunning.current = true;
    if (!running && wasRunning.current && status.data) {
      wasRunning.current = false;
      qc.invalidateQueries({ queryKey: ["system-info"] });
      setCheck(null);
    }
  }, [running, status.data, qc]);

  const checkMutation = useMutation({
    mutationFn: () => api<UpdateCheck>("/system/check-updates", { method: "POST" }),
    onSuccess: setCheck,
  });

  const updateMutation = useMutation({
    mutationFn: (channel: string) => api("/system/update", { method: "POST", body: { channel } }),
    onSuccess: () => {
      wasRunning.current = true;
      qc.setQueryData<UpdateStatus>(["update-status"], (s) => ({ ...(s ?? { log: [] }), state: "running", message: "Starting" }));
      status.refetch();
    },
  });

  // The Info dialog checks automatically when it opens.
  const autoChecked = useRef(false);
  useEffect(() => {
    if (compact && !autoChecked.current) {
      autoChecked.current = true;
      checkMutation.mutate();
    }
  }, [compact]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = (channel: string, isCurrent: boolean) => {
    const name = channelLabel(channel, t);
    const ok = window.confirm(isCurrent ? t("system.confirmUpdate") : t("system.confirmSwitch", { channel: name }));
    if (ok) updateMutation.mutate(channel);
  };

  const state = status.data?.state ?? "idle";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted">
          {check ? t("system.checkedAt", { time: formatDate(check.checked_at, i18n.language) }) : t("system.channels")}
        </div>
        <Button variant="outline" size="sm" onClick={() => checkMutation.mutate()} loading={checkMutation.isPending} disabled={running}>
          {!checkMutation.isPending && <RefreshCw className="h-4 w-4" />}
          {t("system.check")}
        </Button>
      </div>

      {checkMutation.isError && <Alert tone="danger">{errorMessage(t, checkMutation.error)}</Alert>}
      {updateMutation.isError && <Alert tone="danger">{errorMessage(t, updateMutation.error)}</Alert>}

      <div className="grid gap-3 sm:grid-cols-2">
        {CHANNELS.map((channel) => {
          const remote = check?.channels[channel];
          const isCurrent = (check?.current.channel ?? info?.channel) === channel;
          return (
            <div
              key={channel}
              className={cn(
                "rounded-xl border p-4",
                isCurrent ? "border-lucht bg-lucht/10" : "border-line",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold">{channelLabel(channel, t)}</div>
                {isCurrent && <Badge tone="brand">{t("system.current")}</Badge>}
              </div>
              {!compact && (
                <p className="mt-1 text-xs text-muted">{channel === "main" ? t("system.productionHint") : t("system.testHint")}</p>
              )}
              <div className="mt-3 text-sm">
                {remote ? (
                  <>
                    <span className="font-mono">{remote.version}</span>{" "}
                    <span className="font-mono text-xs text-muted">{remote.commit}</span>
                    <div className="text-xs text-muted">{formatDate(remote.commit_date, i18n.language)}</div>
                  </>
                ) : (
                  <span className="text-muted">–</span>
                )}
              </div>
              {remote && (
                <div className="mt-3">
                  {isCurrent ? (
                    remote.update_available ? (
                      <Button size="sm" onClick={() => start(channel, true)} disabled={running}>
                        <Download className="h-4 w-4" />
                        {t("system.update")}
                      </Button>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-sm text-online">
                        <CheckCircle2 className="h-4 w-4" /> {t("system.upToDate")}
                      </span>
                    )
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => start(channel, false)} disabled={running}>
                      <ArrowRightLeft className="h-4 w-4" />
                      {t("system.switchTo", { channel: channelLabel(channel, t) })}
                    </Button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {state !== "idle" && (
        <Alert tone={state === "failed" ? "danger" : state === "success" ? "success" : "info"}>
          <div className="flex items-center gap-2 font-medium">
            {running && <Loader2 className="h-4 w-4 animate-spin" />}
            {t(`system.states.${state}`)}
          </div>
          {status.data?.message && <div className="mt-0.5">{status.data.message}</div>}
        </Alert>
      )}

      {!compact && status.data?.log?.length ? (
        <details className="rounded-lg border border-line">
          <summary className="cursor-pointer px-4 py-2 text-sm font-medium">{t("system.log")}</summary>
          <pre className="max-h-80 overflow-auto rounded-b-md bg-nacht px-4 py-3 text-xs leading-relaxed text-white/85">{status.data.log.join("\n")}</pre>
        </details>
      ) : null}
    </div>
  );
}
