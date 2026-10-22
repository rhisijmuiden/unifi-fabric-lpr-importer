import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { CalendarClock, FileSpreadsheet, Globe, Pencil, Play, Plus, ScrollText, Server, Trash2, Wifi } from "lucide-react";
import { api, type BackupSchedule, type Console, type ImportField, type ImportSchedule, type ImportScheduleTest, type Job } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { useMe } from "@/lib/auth";
import { cn, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Alert, Badge, Dialog, PageHeader } from "@/components/ui/misc";
import { Checkbox, useCanEdit } from "@/components/vehicles";
import { JobDialog } from "@/components/JobDialog";
import { ScheduleEditor } from "@/components/ScheduleEditor";

type Protocol = ImportSchedule["protocol"];
const PORTS: Record<Protocol, number> = { url: 443, ftp: 21, ftps: 21, scp: 22 };
const FIELDS: ImportField[] = ["plate", "department", "location", "group_name", "description"];
const DAILY: BackupSchedule = { enabled: true, frequency: "daily", time: "06:00", weekday: 0, monthday: 1 };

const splitList = (value: string) =>
  value
    .split(/[,;\n]+/)
    .map((v) => v.trim())
    .filter(Boolean);

function sourceLabel(s: Pick<ImportSchedule, "protocol" | "url" | "host" | "remote_path" | "filename">) {
  if (s.protocol === "url") return s.url;
  const path = [s.remote_path.replace(/\/$/, ""), s.filename].filter(Boolean).join("/");
  return `${s.protocol}://${s.host}/${path.replace(/^\//, "")}`;
}

function StatusBadge({ status }: { status: ImportSchedule["last_status"] }) {
  const { t } = useTranslation();
  if (!status) return <Badge>{t("schedules.never")}</Badge>;
  const tone = status === "ok" ? "success" : status === "unchanged" ? "neutral" : "danger";
  return <Badge tone={tone}>{t(`schedules.status.${status}`)}</Badge>;
}

// ---------------------------------------------------------------- test result

function TestPanel({ result }: { result: ImportScheduleTest }) {
  const { t } = useTranslation();
  if (!result.ok) {
    const key = `schedules.fetchErrors.${result.code}`;
    const hint = t(key);
    const fallback = t(`backup.remoteErrors.${result.code}`);
    return (
      <Alert tone="danger">
        <div className="font-semibold">{t("schedules.testFailed")}</div>
        <div>{hint !== key ? hint : fallback !== `backup.remoteErrors.${result.code}` ? fallback : result.message}</div>
        {result.message && <div className="mt-1 break-all font-mono text-xs opacity-80">{result.message}</div>}
      </Alert>
    );
  }
  return (
    <div className="space-y-3">
      <Alert tone="success">
        <div className="font-semibold">{t("schedules.testOk", { columns: result.headers?.length ?? 0, size: ((result.bytes ?? 0) / 1024).toFixed(1) })}</div>
        {result.host_key && <div className="mt-1 break-all font-mono text-xs">{t("backup.hostKey")}: {result.host_key}</div>}
      </Alert>
      {result.missing_columns && <Alert tone="warning">{t("schedules.missingColumns", { columns: result.missing_columns.join(", ") })}</Alert>}
      {result.summary && (
        <div className="rounded-lg bg-surface p-4 text-sm">
          <div className="font-bold">{t("schedules.wouldDo")}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone="brand">{t("schedules.plan.total", { count: result.summary.total })}</Badge>
            <Badge tone="success">{t("schedules.plan.new", { count: result.summary.new })}</Badge>
            <Badge>{t("schedules.plan.changed", { count: result.summary.changed })}</Badge>
            {!!result.summary.invalid && <Badge tone="warning">{t("schedules.plan.invalid", { count: result.summary.invalid })}</Badge>}
            {!!result.summary.remove && <Badge tone="danger">{t("schedules.plan.remove", { count: result.summary.remove })}</Badge>}
          </div>
          {!!result.consoles?.length && (
            <ul className="mt-3 space-y-1 text-xs text-muted">
              {result.consoles.filter((c) => c.selected).map((c) => (
                <li key={c.id}>
                  <span className="font-semibold text-ink">{c.name}</span>: {t("import.toAdd", { count: c.add })} · {t("import.alreadyPresent", { count: c.present })}
                  {!!c.remove && <> · {t("import.toRemove", { count: c.remove })}</>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- dialog

function ScheduleDialog({ schedule, onClose }: { schedule: ImportSchedule | "new"; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isNew = schedule === "new";
  const existing = isNew ? null : schedule;
  const consoles = useQuery({ queryKey: ["consoles"], queryFn: () => api<Console[]>("/consoles") });
  const ssh = useQuery({ queryKey: ["backup-settings"], queryFn: () => api<{ ssh_public_key: string }>("/backup/settings") });
  const [form, setForm] = useState({
    name: existing?.name ?? "",
    is_enabled: existing?.is_enabled ?? true,
    protocol: existing?.protocol ?? ("url" as Protocol),
    url: existing?.url ?? "",
    host: existing?.host ?? "",
    port: existing?.port ?? 443,
    username: existing?.username ?? "",
    password: "",
    auth_method: existing?.auth_method ?? ("password" as ImportSchedule["auth_method"]),
    remote_path: existing?.remote_path ?? "",
    filename: existing?.filename ?? "",
    ftps_implicit: existing?.ftps_implicit ?? false,
    verify_tls: existing?.verify_tls ?? true,
    passive: existing?.passive ?? true,
    mapping: existing?.mapping ?? {},
    defaults: existing?.defaults ?? {},
    console_ids: existing?.console_ids ?? null,
    mode: existing?.mode ?? ("upsert" as ImportSchedule["mode"]),
    max_remove: existing?.max_remove ?? 25,
    skip_unchanged: existing?.skip_unchanged ?? true,
    schedule: existing?.schedule ?? DAILY,
  });
  const [locations, setLocations] = useState((existing?.filter_locations ?? []).join(", "));
  const [departments, setDepartments] = useState((existing?.filter_departments ?? []).join(", "));
  const [headers, setHeaders] = useState<string[]>(Object.values(existing?.mapping ?? {}).filter(Boolean) as string[]);
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const active = consoles.data?.filter((c) => c.is_active) ?? [];

  const changeProtocol = (protocol: Protocol) =>
    setForm((f) => ({ ...f, protocol, port: f.port === PORTS[f.protocol] || (f.ftps_implicit && f.port === 990) ? PORTS[protocol] : f.port }));

  const body = () => ({
    ...form,
    port: form.protocol === "url" ? null : form.port,
    password: form.password || (isNew ? "" : null),
    host_key: null,
    filter_locations: splitList(locations),
    filter_departments: splitList(departments),
  });
  const test = useMutation({
    mutationFn: () => api<ImportScheduleTest>("/import/schedules/test", { method: "POST", body: { ...body(), schedule_id: existing?.id ?? null } }),
    onSuccess: (r) => {
      if (!r.ok || !r.headers) return;
      setHeaders(r.headers);
      // First test: take the suggested columns for fields that are not mapped yet.
      setForm((f) => ({ ...f, mapping: { ...r.suggested, ...Object.fromEntries(Object.entries(f.mapping).filter(([, v]) => v && r.headers!.includes(v))) } }));
    },
  });
  const save = useMutation({
    mutationFn: () => (isNew ? api("/import/schedules", { method: "POST", body: body() }) : api(`/import/schedules/${existing!.id}`, { method: "PUT", body: body() })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["import-schedules"] });
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  const isFile = form.protocol !== "url";
  const allConsoles = form.console_ids === null;
  const toggleConsole = (id: number, on: boolean) => {
    const current = form.console_ids ?? active.map((c) => c.id);
    set("console_ids", on ? [...current, id] : current.filter((x) => x !== id));
  };

  return (
    <Dialog open onClose={onClose} title={isNew ? t("schedules.add") : existing!.name} xl>
      <form onSubmit={submit} className="space-y-6">
        {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "schedules")}</Alert>}
        <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
          <Field label={t("schedules.name")}>
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Lobster export" required />
          </Field>
          <Switch checked={form.is_enabled} onChange={(v) => set("is_enabled", v)} label={t("common.active")} />
        </div>

        <section className="grid gap-6 md:grid-cols-2">
          <div className="space-y-4">
            <h3 className="text-sm font-bold">1. {t("schedules.sourceTitle")}</h3>
            <div className="grid grid-cols-4 gap-2">
              {(["url", "scp", "ftps", "ftp"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => changeProtocol(p)}
                  className={cn("rounded-md px-2 py-2 text-sm font-semibold ring-1", form.protocol === p ? "bg-primary text-primary-ink ring-primary" : "text-muted ring-line hover:text-ink")}
                >
                  {t(`schedules.protocols.${p}`)}
                </button>
              ))}
            </div>
            {form.protocol === "ftp" && <Alert tone="warning">{t("backup.ftpWarning")}</Alert>}
            {form.protocol === "url" ? (
              <Field label={t("schedules.url")} hint={t("schedules.urlHint")}>
                <Input value={form.url} onChange={(e) => set("url", e.target.value)} placeholder="https://export.example.com/vehicles.csv" required />
              </Field>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-[1fr_7rem]">
                  <Field label={t("backup.host")}>
                    <Input value={form.host} onChange={(e) => set("host", e.target.value)} placeholder="sftp.example.com" required />
                  </Field>
                  <Field label={t("backup.port")}>
                    <Input type="number" min={1} max={65535} value={form.port} onChange={(e) => set("port", Number(e.target.value))} />
                  </Field>
                </div>
                {form.protocol === "ftps" && (
                  <Field label={t("backup.ftpsMode")}>
                    <Select
                      value={form.ftps_implicit ? "implicit" : "explicit"}
                      onChange={(e) => {
                        const implicit = e.target.value === "implicit";
                        setForm((f) => ({ ...f, ftps_implicit: implicit, port: implicit && f.port === 21 ? 990 : !implicit && f.port === 990 ? 21 : f.port }));
                      }}
                    >
                      <option value="explicit">{t("backup.ftpsExplicit")}</option>
                      <option value="implicit">{t("backup.ftpsImplicit")}</option>
                    </Select>
                  </Field>
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label={t("schedules.folder")}>
                    <Input value={form.remote_path} onChange={(e) => set("remote_path", e.target.value)} placeholder="export" />
                  </Field>
                  <Field label={t("schedules.filename")}>
                    <Input value={form.filename} onChange={(e) => set("filename", e.target.value)} placeholder="vehicles.csv" required />
                  </Field>
                </div>
              </>
            )}
            <Field label={t("backup.username")} hint={form.protocol === "url" ? t("schedules.basicAuthHint") : undefined}>
              <Input value={form.username} onChange={(e) => set("username", e.target.value)} autoComplete="off" />
            </Field>
            {form.protocol === "scp" && (
              <Field label={t("backup.authMethod")}>
                <Select value={form.auth_method} onChange={(e) => set("auth_method", e.target.value as ImportSchedule["auth_method"])}>
                  <option value="key">{t("backup.authKey")}</option>
                  <option value="password">{t("backup.authPassword")}</option>
                </Select>
              </Field>
            )}
            {form.protocol === "scp" && form.auth_method === "key" && ssh.data && (
              <div className="rounded-lg bg-surface p-4">
                <p className="text-xs text-muted">{t("backup.sshKeyHelp")}</p>
                <textarea readOnly value={ssh.data.ssh_public_key} className="mt-2 h-20 w-full resize-none rounded-md border border-line bg-raised p-2 font-mono text-xs" onFocus={(e) => e.target.select()} />
              </div>
            )}
            {(form.protocol !== "scp" || form.auth_method === "password") && (
              <Field label={t("backup.password")} hint={existing?.password_set ? t("common.unchanged") : undefined}>
                <Input type="password" autoComplete="new-password" value={form.password} onChange={(e) => set("password", e.target.value)} placeholder={existing?.password_set ? "••••••••" : ""} />
              </Field>
            )}
            {(form.protocol === "url" || form.protocol === "ftps") && (
              <Switch checked={form.verify_tls} onChange={(v) => set("verify_tls", v)} label={t("backup.verifyTls")} description={t("backup.verifyTlsHint")} />
            )}
            {isFile && form.protocol !== "scp" && <Switch checked={form.passive} onChange={(v) => set("passive", v)} label={t("backup.passive")} description={t("backup.passiveHint")} />}
            <Button type="button" variant="outline" loading={test.isPending} disabled={isFile ? !form.host || !form.filename : !form.url} onClick={() => test.mutate()}>
              <Wifi className="h-4 w-4" />
              {t("schedules.test")}
            </Button>
            {test.data && <TestPanel result={test.data} />}
            {test.isError && <Alert tone="danger">{errorMessage(t, test.error, "schedules")}</Alert>}
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-bold">2. {t("schedules.columnsTitle")}</h3>
            {!headers.length && <p className="text-sm text-muted">{t("schedules.columnsHint")}</p>}
            <div className="space-y-3">
              {FIELDS.map((f) => (
                <div key={f} className="grid grid-cols-[8rem_1fr_1fr] items-center gap-2">
                  <div className="text-sm font-semibold">
                    {t(`import.fields.${f}`)}
                    {(f === "plate" || f === "department") && <span className="text-offline"> *</span>}
                  </div>
                  {headers.length ? (
                    <Select value={form.mapping[f] ?? ""} onChange={(e) => set("mapping", { ...form.mapping, [f]: e.target.value || undefined })}>
                      <option value="">{t("import.noColumn")}</option>
                      {headers.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <Input value={form.mapping[f] ?? ""} onChange={(e) => set("mapping", { ...form.mapping, [f]: e.target.value || undefined })} placeholder={t("schedules.columnName")} />
                  )}
                  {f !== "plate" ? (
                    <Input value={form.defaults[f] ?? ""} onChange={(e) => set("defaults", { ...form.defaults, [f]: e.target.value })} placeholder={t("import.defaultPlaceholder")} />
                  ) : (
                    <span />
                  )}
                </div>
              ))}
            </div>

            <h3 className="pt-2 text-sm font-bold">3. {t("schedules.filterTitle")}</h3>
            <Field label={t("schedules.filterLocations")} hint={t("schedules.filterHint")}>
              <Input value={locations} onChange={(e) => setLocations(e.target.value)} placeholder="Wognum, Zwaagdijk" />
            </Field>
            <Field label={t("schedules.filterDepartments")}>
              <Input value={departments} onChange={(e) => setDepartments(e.target.value)} placeholder="Netwerktransport" />
            </Field>
          </div>
        </section>

        <section className="grid gap-6 md:grid-cols-2">
          <div className="space-y-4">
            <h3 className="text-sm font-bold">4. {t("schedules.targetTitle")}</h3>
            <Switch checked={allConsoles} onChange={(v) => set("console_ids", v ? null : active.map((c) => c.id))} label={t("schedules.allConsoles")} description={t("schedules.allConsolesHint")} />
            {!allConsoles && (
              <div className="space-y-2 rounded-lg border border-line p-3">
                {active.map((c) => (
                  <label key={c.id} className="flex items-center gap-2 text-sm">
                    <Checkbox checked={form.console_ids!.includes(c.id)} onChange={(on) => toggleConsole(c.id, on)} />
                    {c.name}
                  </label>
                ))}
              </div>
            )}
            <Field label={t("import.mode")}>
              <Select value={form.mode} onChange={(e) => set("mode", e.target.value as ImportSchedule["mode"])}>
                <option value="upsert">{t("import.modes.upsert")}</option>
                <option value="full">{t("import.modes.full")}</option>
              </Select>
            </Field>
            <p className="text-xs text-muted">{t(form.mode === "full" ? "import.modes.fullHint" : "import.modes.upsertHint")}</p>
            {form.mode === "full" && (
              <Field label={t("schedules.maxRemove")} hint={t("schedules.maxRemoveHint")}>
                <Input type="number" min={0} value={form.max_remove} onChange={(e) => set("max_remove", Number(e.target.value))} />
              </Field>
            )}
            <Switch checked={form.skip_unchanged} onChange={(v) => set("skip_unchanged", v)} label={t("schedules.skipUnchanged")} description={t("schedules.skipUnchangedHint")} />
          </div>
          <div className="space-y-4">
            <h3 className="text-sm font-bold">5. {t("schedules.whenTitle")}</h3>
            <ScheduleEditor label={t("schedules.runOnSchedule")} value={form.schedule} next={existing?.next_run ?? null} onChange={(v) => set("schedule", v)} />
          </div>
        </section>

        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" loading={save.isPending}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------- page

export function ImportSchedulesPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const canRun = useCanEdit();
  const [editing, setEditing] = useState<ImportSchedule | "new" | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const list = useQuery({ queryKey: ["import-schedules"], queryFn: () => api<ImportSchedule[]>("/import/schedules"), refetchInterval: 15000 });
  const run = useMutation({
    mutationFn: (s: ImportSchedule) => api<Job>(`/import/schedules/${s.id}/run`, { method: "POST" }),
    onSuccess: (job) => setJobId(job.id),
  });
  const remove = useMutation({
    mutationFn: (s: ImportSchedule) => api(`/import/schedules/${s.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["import-schedules"] }),
  });

  return (
    <>
      <PageHeader
        title={t("schedules.title")}
        description={t("schedules.description")}
        action={
          isAdmin && (
            <Button onClick={() => setEditing("new")}>
              <Plus className="h-4 w-4" />
              {t("schedules.add")}
            </Button>
          )
        }
      />
      {run.isError && (
        <div className="mb-4">
          <Alert tone="danger">{errorMessage(t, run.error, "schedules")}</Alert>
        </div>
      )}
      {list.data && !list.data.length && (
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-12 text-center">
            <CalendarClock className="h-10 w-10 text-muted" />
            <div className="font-semibold">{t("schedules.emptyTitle")}</div>
            <p className="max-w-lg text-sm text-muted">{t("schedules.emptyBody")}</p>
          </CardBody>
        </Card>
      )}
      <div className="grid gap-4">
        {list.data?.map((s) => (
          <Card key={s.id}>
            <CardHeader
              title={
                <span className="flex flex-wrap items-center gap-2">
                  {s.protocol === "url" ? <Globe className="h-4 w-4 text-muted" /> : <Server className="h-4 w-4 text-muted" />}
                  {s.name}
                  {!s.is_enabled && <Badge>{t("common.inactive")}</Badge>}
                  {s.mode === "full" && <Badge tone="warning">{t("import.modes.full")}</Badge>}
                </span>
              }
              description={<span className="break-all font-mono text-xs">{sourceLabel(s)}</span>}
              action={
                <div className="flex flex-wrap gap-1">
                  {canRun && (
                    <Button variant="outline" size="sm" loading={run.isPending && run.variables?.id === s.id} onClick={() => run.mutate(s)}>
                      <Play className="h-4 w-4" />
                      {t("schedules.runNow")}
                    </Button>
                  )}
                  {s.last_job_id && (
                    <Button variant="ghost" size="sm" onClick={() => setJobId(s.last_job_id)} title={t("schedules.lastReport")}>
                      <ScrollText className="h-4 w-4" />
                    </Button>
                  )}
                  {isAdmin && (
                    <>
                      <Button variant="ghost" size="sm" onClick={() => setEditing(s)} aria-label={t("common.edit")}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => window.confirm(t("common.confirmDelete", { name: s.name })) && remove.mutate(s)} aria-label={t("common.delete")}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                </div>
              }
            />
            <CardBody className="grid gap-4 text-sm sm:grid-cols-3">
              <div>
                <div className="text-xs text-muted">{t("schedules.nextRun")}</div>
                <div className="mt-0.5 font-semibold">{s.next_run ? formatDate(s.next_run, i18n.language) : t("schedules.notScheduled")}</div>
              </div>
              <div>
                <div className="text-xs text-muted">{t("schedules.lastRun")}</div>
                <div className="mt-0.5 flex items-center gap-2 font-semibold">
                  {s.last_run_at ? formatDate(s.last_run_at, i18n.language) : t("common.never")}
                  <StatusBadge status={s.last_status} />
                </div>
              </div>
              <div>
                <div className="text-xs text-muted">{t("schedules.columns")}</div>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  <FileSpreadsheet className="h-4 w-4 text-muted" />
                  {Object.entries(s.mapping).map(([f, h]) => (
                    <span key={f} className="text-xs">
                      {t(`import.fields.${f}`)} ← <span className="font-mono">{h}</span>
                    </span>
                  ))}
                </div>
              </div>
              {s.last_status === "failed" && s.last_message && (
                <div className="sm:col-span-3">
                  <Alert tone="danger">{s.last_message}</Alert>
                </div>
              )}
            </CardBody>
          </Card>
        ))}
      </div>
      {editing && <ScheduleDialog schedule={editing} onClose={() => setEditing(null)} />}
      <JobDialog jobId={jobId} onClose={() => setJobId(null)} onFinished={() => qc.invalidateQueries({ queryKey: ["import-schedules"] })} />
    </>
  );
}
