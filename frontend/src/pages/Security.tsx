import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Lock, ShieldCheck } from "lucide-react";
import { api, type SecuritySettings, type SessionInfo } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Alert, Badge, PageHeader } from "@/components/ui/misc";
import { SessionsList } from "@/components/SessionsList";

type Editable = Omit<SecuritySettings, "https" | "cookie_secure" | "secret_key_ok">;

function NumberField({ label, hint, value, min, max, onChange }: { label: string; hint?: string; value: number; min: number; max: number; onChange: (v: number) => void }) {
  return (
    <Field label={label} hint={hint}>
      <Input type="number" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </Field>
  );
}

function Check({ ok, label, hint }: { ok: boolean; label: string; hint: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-start gap-3 py-2">
      <Badge tone={ok ? "success" : "warning"}>{ok ? t("security.ok") : t("security.attention")}</Badge>
      <div className="min-w-0 flex-1 text-sm">
        <div className="font-semibold">{label}</div>
        <div className="text-xs text-muted">{hint}</div>
      </div>
    </div>
  );
}

export function SecurityPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["security"], queryFn: () => api<SecuritySettings>("/security/settings") });
  const sessions = useQuery({ queryKey: ["security-sessions"], queryFn: () => api<SessionInfo[]>("/security/sessions"), refetchInterval: 30000 });
  const [form, setForm] = useState<Editable | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (settings.data && !form) setForm(settings.data);
  }, [settings.data, form]);
  const save = useMutation({
    mutationFn: (body: Editable) => api<SecuritySettings>("/security/settings", { method: "PUT", body }),
    onSuccess: (d) => {
      qc.setQueryData(["security"], d);
      setSaved(true);
    },
  });
  const end = useMutation({
    mutationFn: (s: SessionInfo) => api(`/security/sessions/${s.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["security-sessions"] }),
  });
  const set = <K extends keyof Editable>(k: K, v: Editable[K]) => {
    setSaved(false);
    setForm((f) => (f ? { ...f, [k]: v } : f));
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (form) {
      const { session_hours, idle_minutes, login_max_attempts, login_lock_minutes, api_requests_per_minute } = form;
      save.mutate({ session_hours, idle_minutes, login_max_attempts, login_lock_minutes, api_requests_per_minute });
    }
  };
  const s = settings.data;

  return (
    <>
      <PageHeader title={t("security.title")} description={t("security.description")} />
      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        {form && (
          <form onSubmit={submit} className="space-y-6">
            <Card>
              <CardHeader title={t("security.sessionsTitle")} description={t("security.sessionsHint")} />
              <CardBody className="grid gap-4 sm:grid-cols-2">
                <NumberField label={t("security.sessionHours")} hint={t("security.sessionHoursHint")} value={form.session_hours} min={1} max={720} onChange={(v) => set("session_hours", v)} />
                <NumberField label={t("security.idleMinutes")} hint={t("security.idleMinutesHint")} value={form.idle_minutes} min={0} max={10080} onChange={(v) => set("idle_minutes", v)} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title={t("security.rateTitle")} description={t("security.rateHint")} />
              <CardBody className="grid gap-4 sm:grid-cols-2">
                <NumberField label={t("security.maxAttempts")} hint={t("security.maxAttemptsHint")} value={form.login_max_attempts} min={3} max={100} onChange={(v) => set("login_max_attempts", v)} />
                <NumberField label={t("security.lockMinutes")} value={form.login_lock_minutes} min={1} max={1440} onChange={(v) => set("login_lock_minutes", v)} />
                <NumberField label={t("security.apiPerMinute")} hint={t("security.apiPerMinuteHint")} value={form.api_requests_per_minute} min={10} max={100000} onChange={(v) => set("api_requests_per_minute", v)} />
              </CardBody>
            </Card>
            {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "security")}</Alert>}
            <div className="flex items-center justify-end gap-3">
              {saved && <span className="text-sm text-online">{t("common.saved")}</span>}
              <Button type="submit" loading={save.isPending}>
                {t("common.save")}
              </Button>
            </div>
          </form>
        )}
        {s && (
          <Card className="self-start">
            <CardHeader title={<span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" />{t("security.checksTitle")}</span>} />
            <CardBody className="divide-y divide-line">
              <Check ok={s.https} label={t("security.https")} hint={t(s.https ? "security.httpsOk" : "security.httpsHint")} />
              {s.https && <Check ok={s.cookie_secure} label={t("security.cookieSecure")} hint={t(s.cookie_secure ? "security.cookieSecureOk" : "security.cookieSecureHint")} />}
              <Check ok={s.secret_key_ok} label={t("security.secretKey")} hint={t(s.secret_key_ok ? "security.secretKeyOk" : "security.secretKeyHint")} />
              <div className="flex items-start gap-3 pt-3 text-xs text-muted">
                <Lock className="mt-0.5 h-4 w-4 shrink-0" />
                {t("security.encryptedNote")}
              </div>
            </CardBody>
          </Card>
        )}
      </div>
      <Card className="mt-6">
        <CardHeader title={t("security.activeSessions")} description={t("security.activeSessionsHint")} />
        <CardBody>
          {end.isError && <Alert tone="danger">{errorMessage(t, end.error, "security")}</Alert>}
          {sessions.data && <SessionsList sessions={sessions.data} showUser onEnd={(x) => end.mutate(x)} ending={end.isPending ? end.variables?.id : null} />}
        </CardBody>
      </Card>
    </>
  );
}
