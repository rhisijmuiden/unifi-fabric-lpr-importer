import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Pencil, Plus, RefreshCw, Server, Trash2, Wifi, XCircle } from "lucide-react";
import { api, type Console, type ConsoleTestResult, type Job } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Switch } from "@/components/ui/form";
import { Alert, Badge, Dialog, PageHeader } from "@/components/ui/misc";
import { JobDialog } from "@/components/JobDialog";
import { useCanEdit } from "@/components/vehicles";

function TestResult({ result }: { result: ConsoleTestResult }) {
  const { t } = useTranslation();
  if (result.ok) {
    return <Alert tone="success">{t("consoles.testOk", { users: result.users, groups: result.groups })}</Alert>;
  }
  const key = `consoles.testErrors.${result.code}`;
  const hint = t(key);
  return (
    <Alert tone="danger">
      <div className="font-semibold">{t("consoles.testFailed")}</div>
      <div>{hint !== key ? hint : result.message}</div>
    </Alert>
  );
}

function HelpSteps() {
  const { t } = useTranslation();
  const steps = t("consoles.help.steps", { returnObjects: true }) as { title: string; body: string }[];
  return (
    <div className="rounded-lg bg-surface p-5">
      <div className="mb-3 text-sm font-bold">{t("consoles.help.title")}</div>
      <ol className="space-y-3">
        {steps.map((s, i) => (
          <li key={s.title} className="flex gap-3 text-sm">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-nacht text-xs font-bold text-white dark:bg-lucht dark:text-nacht">{i + 1}</span>
            <div>
              <div className="font-semibold">{s.title}</div>
              <div className="mt-0.5 text-muted">{s.body}</div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ConsoleDialog({ console: existing, onClose }: { console: Console | "new"; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isNew = existing === "new";
  const c = isNew ? null : existing;
  const [form, setForm] = useState({
    name: c?.name ?? "",
    location: c?.location ?? "",
    host: c?.host ?? "",
    port: c?.port ?? 12445,
    api_token: "",
    verify_tls: c?.verify_tls ?? false,
    is_active: c?.is_active ?? true,
    sort_order: c?.sort_order ?? 0,
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const test = useMutation({
    mutationFn: () =>
      api<ConsoleTestResult>("/consoles/test", {
        method: "POST",
        body: { host: form.host, port: form.port, verify_tls: form.verify_tls, api_token: form.api_token || null, console_id: c?.id ?? null },
      }),
  });
  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, api_token: form.api_token || (isNew ? "" : null) };
      return isNew ? api("/consoles", { method: "POST", body }) : api(`/consoles/${c!.id}`, { method: "PUT", body });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["consoles"] });
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <Dialog open onClose={onClose} title={isNew ? t("consoles.add") : c!.name} xl>
      <div className="grid gap-6 md:grid-cols-[1fr_1fr]">
        <form onSubmit={submit} className="space-y-4">
          {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "consoles")}</Alert>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("consoles.name")}>
              <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Wognum" required />
            </Field>
            <Field label={t("consoles.location")} hint={t("consoles.locationHint")}>
              <Input value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="Wognum" />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-[1fr_7rem]">
            <Field label={t("consoles.host")} hint={t("consoles.hostHint")}>
              <Input value={form.host} onChange={(e) => set("host", e.target.value)} placeholder="192.168.1.1" required />
            </Field>
            <Field label={t("consoles.port")}>
              <Input type="number" value={form.port} onChange={(e) => set("port", Number(e.target.value))} min={1} max={65535} />
            </Field>
          </div>
          <Field label={t("consoles.token")} hint={c?.api_token_set ? t("common.unchanged") : t("consoles.tokenHint")}>
            <Input type="password" autoComplete="off" value={form.api_token} onChange={(e) => set("api_token", e.target.value)} required={isNew} />
          </Field>
          <Switch checked={form.verify_tls} onChange={(v) => set("verify_tls", v)} label={t("consoles.verifyTls")} description={t("consoles.verifyTlsHint")} />
          <Switch checked={form.is_active} onChange={(v) => set("is_active", v)} label={t("common.active")} description={t("consoles.activeHint")} />
          {test.data && <TestResult result={test.data} />}
          {test.isError && <Alert tone="danger">{errorMessage(t, test.error, "consoles")}</Alert>}
          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button type="button" variant="outline" loading={test.isPending} disabled={!form.host} onClick={() => test.mutate()}>
              <Wifi className="h-4 w-4" />
              {t("consoles.test")}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={save.isPending}>
              {t("common.save")}
            </Button>
          </div>
        </form>
        <HelpSteps />
      </div>
    </Dialog>
  );
}

function StatusBadge({ c }: { c: Console }) {
  const { t } = useTranslation();
  if (!c.is_active) return <Badge>{t("common.inactive")}</Badge>;
  if (c.last_test_ok === true) return <Badge tone="success">{t("consoles.connected")}</Badge>;
  if (c.last_test_ok === false) return <Badge tone="danger">{t("consoles.unreachable")}</Badge>;
  return <Badge tone="warning">{t("consoles.notTested")}</Badge>;
}

function AccessSettings() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings", "access"], queryFn: () => api<{ plate_notation: string; delete_vehicle_users: boolean }>("/settings/access") });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api("/settings/access", { method: "PUT", body: { ...data, ...body } }),
    onSuccess: (d) => qc.setQueryData(["settings", "access"], d),
  });
  if (!data) return null;
  return (
    <Card className="mt-6">
      <CardHeader title={t("consoles.settings.title")} description={t("consoles.settings.description")} />
      <CardBody className="space-y-5">
        <div>
          <div className="text-sm font-semibold">{t("consoles.settings.notation")}</div>
          <div className="mt-0.5 text-sm text-muted">{t("consoles.settings.notationHint")}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {(["compact", "official"] as const).map((n) => (
              <button
                key={n}
                onClick={() => save.mutate({ plate_notation: n })}
                className={
                  data.plate_notation === n
                    ? "rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-ink"
                    : "rounded-md px-3 py-2 text-sm font-semibold text-muted ring-1 ring-line hover:text-ink"
                }
              >
                {t(`consoles.settings.${n}`)}
              </button>
            ))}
          </div>
        </div>
        <Switch
          checked={data.delete_vehicle_users}
          onChange={(v) => save.mutate({ delete_vehicle_users: v })}
          label={t("consoles.settings.deleteUsers")}
          description={t("consoles.settings.deleteUsersHint")}
        />
      </CardBody>
    </Card>
  );
}

export function ConsolesPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const canEdit = useCanEdit();
  const [editing, setEditing] = useState<Console | "new" | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const consoles = useQuery({ queryKey: ["consoles"], queryFn: () => api<Console[]>("/consoles") });
  const test = useMutation({
    mutationFn: (c: Console) => api<ConsoleTestResult>(`/consoles/${c.id}/test`, { method: "POST" }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["consoles"] }),
  });
  const scan = useMutation({
    mutationFn: (ids: number[] | null) => api<Job>("/consoles/scan", { method: "POST", body: { console_ids: ids } }),
    onSuccess: (job) => setJobId(job.id),
  });
  const remove = useMutation({
    mutationFn: (c: Console) => api(`/consoles/${c.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["consoles"] }),
  });

  return (
    <>
      <PageHeader
        title={t("consoles.title")}
        description={t("consoles.description")}
        action={
          <div className="flex gap-2">
            {canEdit && !!consoles.data?.length && (
              <Button variant="outline" loading={scan.isPending && scan.variables === null} onClick={() => scan.mutate(null)}>
                <RefreshCw className="h-4 w-4" />
                {t("consoles.scanAll")}
              </Button>
            )}
            {isAdmin && (
              <Button onClick={() => setEditing("new")}>
                <Plus className="h-4 w-4" />
                {t("consoles.add")}
              </Button>
            )}
          </div>
        }
      />
      {consoles.data && !consoles.data.length && (
        <Card className="flex flex-col items-center px-6 py-14 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-lucht/20 text-nacht dark:text-lucht">
            <Server className="h-6 w-6" />
          </div>
          <h2 className="mt-4 font-semibold">{t("consoles.emptyTitle")}</h2>
          <p className="mt-1 max-w-md text-sm text-muted">{t("consoles.emptyBody")}</p>
          {isAdmin && (
            <Button variant="accent" className="mt-5" onClick={() => setEditing("new")}>
              <Plus className="h-4 w-4" />
              {t("consoles.add")}
            </Button>
          )}
        </Card>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {consoles.data?.map((c) => (
          <Card key={c.id} className="flex flex-col">
            <div className="flex items-start gap-3 border-b border-line px-5 py-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-lucht/20 text-nacht dark:text-lucht">
                <Server className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate font-bold">{c.name}</div>
                <div className="truncate font-mono text-xs text-muted">
                  {c.host}:{c.port}
                </div>
              </div>
              <StatusBadge c={c} />
            </div>
            <dl className="flex-1 space-y-2 px-5 py-4 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{t("consoles.location")}</dt>
                <dd className="font-semibold">{c.location || "–"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{t("consoles.platesFound")}</dt>
                <dd className="font-semibold">{c.last_scan_at ? c.plates : "–"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{t("consoles.lastScan")}</dt>
                <dd>{c.last_scan_at ? formatDate(c.last_scan_at, i18n.language) : t("common.never")}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{t("consoles.lastTest")}</dt>
                <dd className="flex items-center gap-1">
                  {c.last_test_ok === true && <CheckCircle2 className="h-3.5 w-3.5 text-online" />}
                  {c.last_test_ok === false && <XCircle className="h-3.5 w-3.5 text-offline" />}
                  {c.last_test_at ? formatDate(c.last_test_at, i18n.language) : t("common.never")}
                </dd>
              </div>
              {c.last_test_ok === false && c.last_test_message && <p className="rounded-md bg-offline/10 px-3 py-2 text-xs text-offline">{c.last_test_message}</p>}
            </dl>
            {canEdit && (
              <div className="flex items-center gap-1 border-t border-line px-3 py-2">
                <Button variant="ghost" size="sm" loading={test.isPending && test.variables?.id === c.id} onClick={() => test.mutate(c)}>
                  <Wifi className="h-4 w-4" />
                  {t("consoles.test")}
                </Button>
                <Button variant="ghost" size="sm" disabled={!c.is_active} onClick={() => scan.mutate([c.id])}>
                  <RefreshCw className="h-4 w-4" />
                  {t("consoles.scan")}
                </Button>
                <div className="flex-1" />
                {isAdmin && (
                  <>
                    <Button variant="ghost" size="icon" onClick={() => setEditing(c)} aria-label={t("common.edit")}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("common.delete")}
                      onClick={() => window.confirm(t("consoles.confirmDelete", { name: c.name })) && remove.mutate(c)}
                    >
                      <Trash2 className="h-4 w-4 text-offline" />
                    </Button>
                  </>
                )}
              </div>
            )}
          </Card>
        ))}
      </div>
      {isAdmin && !!consoles.data?.length && <AccessSettings />}
      {editing !== null && <ConsoleDialog console={editing} onClose={() => setEditing(null)} />}
      <JobDialog
        jobId={jobId}
        onClose={() => setJobId(null)}
        onFinished={() => {
          qc.invalidateQueries({ queryKey: ["consoles"] });
          qc.invalidateQueries({ queryKey: ["vehicles"] });
          qc.invalidateQueries({ queryKey: ["adopt"] });
        }}
      />
    </>
  );
}
