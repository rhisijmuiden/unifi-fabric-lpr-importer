import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  ArchiveRestore,
  CheckCircle2,
  Copy,
  DatabaseBackup,
  Download,
  FolderOpen,
  HardDrive,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
  Wand2,
  Wifi,
  XCircle,
} from "lucide-react";
import {
  api,
  type BackupItem,
  type BackupSchedule,
  type BackupSettings,
  type BackupTarget,
  type BackupTestResult,
  type Job,
} from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { cn, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Alert, Badge, Dialog, PageHeader } from "@/components/ui/misc";
import { JobDialog } from "@/components/JobDialog";

const PORTS = { ftp: 21, ftps: 21, scp: 22 } as const;

function formatSize(bytes: number | null) {
  if (bytes == null) return "–";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function CopyButton({ value }: { value: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <Button type="button" variant="outline" size="sm" onClick={() => navigator.clipboard?.writeText(value).then(() => setCopied(true))}>
      <Copy className="h-4 w-4" />
      {copied ? t("backup.copied") : t("backup.copy")}
    </Button>
  );
}

function TestResult({ result }: { result: BackupTestResult }) {
  const { t } = useTranslation();
  if (result.ok) {
    return (
      <Alert tone="success">
        <div className="font-semibold">{t("backup.testOk", { count: result.backups ?? 0 })}</div>
        {result.host_key && <div className="mt-1 break-all font-mono text-xs">{t("backup.hostKey")}: {result.host_key}</div>}
      </Alert>
    );
  }
  const key = `backup.remoteErrors.${result.code}`;
  const hint = t(key);
  return (
    <Alert tone="danger">
      <div className="font-semibold">{t("backup.testFailed")}</div>
      <div>{hint !== key ? hint : result.message}</div>
      {hint !== key && result.message && <div className="mt-1 break-all font-mono text-xs opacity-80">{result.message}</div>}
    </Alert>
  );
}

// ---------------------------------------------------------------- location dialog

function TargetDialog({ target, sshPublicKey, onClose }: { target: BackupTarget | "new"; sshPublicKey: string; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isNew = target === "new";
  const existing = isNew ? null : target;
  const [form, setForm] = useState({
    name: existing?.name ?? "",
    protocol: existing?.protocol ?? ("scp" as BackupTarget["protocol"]),
    host: existing?.host ?? "",
    port: existing?.port ?? 22,
    username: existing?.username ?? "",
    password: "",
    auth_method: existing?.auth_method ?? ("password" as BackupTarget["auth_method"]),
    remote_path: existing?.remote_path ?? "lpr-importer",
    ftps_implicit: existing?.ftps_implicit ?? false,
    verify_tls: existing?.verify_tls ?? true,
    passive: existing?.passive ?? true,
    is_enabled: existing?.is_enabled ?? true,
  });
  const [forgetHostKey, setForgetHostKey] = useState(false);
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  const changeProtocol = (protocol: BackupTarget["protocol"]) => {
    setForm((f) => {
      const defaultPort = f.port === PORTS[f.protocol] || (f.protocol === "ftps" && f.ftps_implicit && f.port === 990);
      return { ...f, protocol, port: defaultPort ? PORTS[protocol] : f.port };
    });
  };
  const changeImplicit = (implicit: boolean) => {
    setForm((f) => ({ ...f, ftps_implicit: implicit, port: implicit && f.port === 21 ? 990 : !implicit && f.port === 990 ? 21 : f.port }));
  };

  const body = () => ({
    ...form,
    password: form.password || (isNew ? "" : null),
    host_key: forgetHostKey ? "" : null,
  });
  const test = useMutation({
    mutationFn: () => api<BackupTestResult>("/backup/targets/test", { method: "POST", body: { ...body(), target_id: existing?.id ?? null } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backup-targets"] }),
  });
  const save = useMutation({
    mutationFn: () => (isNew ? api("/backup/targets", { method: "POST", body: body() }) : api(`/backup/targets/${existing!.id}`, { method: "PUT", body: body() })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["backup-targets"] });
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  const isFtp = form.protocol !== "scp";

  return (
    <Dialog open onClose={onClose} title={isNew ? t("backup.addTarget") : existing!.name} xl>
      <form onSubmit={submit} className="grid gap-6 md:grid-cols-[1fr_1fr]">
        <div className="space-y-4">
          {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "backup")}</Alert>}
          <Field label={t("backup.targetName")}>
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="NAS Wognum" required />
          </Field>
          <Field label={t("backup.protocol")}>
            <div className="grid grid-cols-3 gap-2">
              {(["scp", "ftps", "ftp"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => changeProtocol(p)}
                  className={cn(
                    "rounded-md px-3 py-2 text-sm font-semibold ring-1",
                    form.protocol === p ? "bg-primary text-primary-ink ring-primary" : "text-muted ring-line hover:text-ink",
                  )}
                >
                  {t(`backup.protocols.${p}`)}
                </button>
              ))}
            </div>
          </Field>
          {form.protocol === "ftp" && <Alert tone="warning">{t("backup.ftpWarning")}</Alert>}
          <div className="grid gap-4 sm:grid-cols-[1fr_7rem]">
            <Field label={t("backup.host")}>
              <Input value={form.host} onChange={(e) => set("host", e.target.value)} placeholder="nas.example.local" required />
            </Field>
            <Field label={t("backup.port")}>
              <Input type="number" min={1} max={65535} value={form.port} onChange={(e) => set("port", Number(e.target.value))} />
            </Field>
          </div>
          {form.protocol === "ftps" && (
            <Field label={t("backup.ftpsMode")}>
              <Select value={form.ftps_implicit ? "implicit" : "explicit"} onChange={(e) => changeImplicit(e.target.value === "implicit")}>
                <option value="explicit">{t("backup.ftpsExplicit")}</option>
                <option value="implicit">{t("backup.ftpsImplicit")}</option>
              </Select>
            </Field>
          )}
          <Field label={t("backup.username")}>
            <Input value={form.username} onChange={(e) => set("username", e.target.value)} autoComplete="off" />
          </Field>
          {form.protocol === "scp" && (
            <Field label={t("backup.authMethod")}>
              <Select value={form.auth_method} onChange={(e) => set("auth_method", e.target.value as BackupTarget["auth_method"])}>
                <option value="key">{t("backup.authKey")}</option>
                <option value="password">{t("backup.authPassword")}</option>
              </Select>
            </Field>
          )}
          {(isFtp || form.auth_method === "password") && (
            <Field label={t("backup.password")} hint={existing?.password_set ? t("common.unchanged") : undefined}>
              <Input
                type="password"
                autoComplete="new-password"
                value={form.password}
                onChange={(e) => set("password", e.target.value)}
                placeholder={existing?.password_set ? "••••••••" : ""}
              />
            </Field>
          )}
          <Field label={t("backup.remotePath")} hint={t("backup.remotePathHint")}>
            <Input value={form.remote_path} onChange={(e) => set("remote_path", e.target.value)} placeholder="lpr-importer" />
          </Field>
          {form.protocol === "ftps" && <Switch checked={form.verify_tls} onChange={(v) => set("verify_tls", v)} label={t("backup.verifyTls")} description={t("backup.verifyTlsHint")} />}
          {isFtp && <Switch checked={form.passive} onChange={(v) => set("passive", v)} label={t("backup.passive")} description={t("backup.passiveHint")} />}
          <Switch checked={form.is_enabled} onChange={(v) => set("is_enabled", v)} label={t("common.active")} description={t("backup.enabledHint")} />
          {test.data && <TestResult result={test.data} />}
          {test.isError && <Alert tone="danger">{errorMessage(t, test.error, "backup")}</Alert>}
          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button type="button" variant="outline" loading={test.isPending} disabled={!form.host} onClick={() => test.mutate()}>
              <Wifi className="h-4 w-4" />
              {t("backup.test")}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={save.isPending}>
              {t("common.save")}
            </Button>
          </div>
        </div>
        <div className="space-y-4">
          {form.protocol === "scp" && form.auth_method === "key" && (
            <div className="rounded-lg bg-surface p-5">
              <div className="text-sm font-bold">{t("backup.sshKeyTitle")}</div>
              <p className="mt-1 text-sm text-muted">{t("backup.sshKeyHelp")}</p>
              <textarea readOnly value={sshPublicKey} className="mt-3 h-24 w-full resize-none rounded-md border border-line bg-raised p-2 font-mono text-xs" onFocus={(e) => e.target.select()} />
              <div className="mt-2">
                <CopyButton value={sshPublicKey} />
              </div>
            </div>
          )}
          {form.protocol === "scp" && existing?.host_key && (
            <div className="rounded-lg bg-surface p-5">
              <div className="text-sm font-bold">{t("backup.hostKey")}</div>
              <p className="mt-1 text-sm text-muted">{t("backup.hostKeyHelp")}</p>
              <div className={cn("mt-3 break-all font-mono text-xs", forgetHostKey && "line-through opacity-60")}>{existing.host_key}</div>
              <Button type="button" variant="ghost" size="sm" className="mt-2" onClick={() => setForgetHostKey((v) => !v)}>
                {forgetHostKey ? t("common.cancel") : t("backup.forgetHostKey")}
              </Button>
            </div>
          )}
          <div className="rounded-lg bg-surface p-5 text-sm">
            <div className="font-bold">{t(`backup.protocolHelp.${form.protocol}.title`)}</div>
            <p className="mt-1 text-muted">{t(`backup.protocolHelp.${form.protocol}.body`)}</p>
          </div>
        </div>
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------- backups on a location

function RestoreConfirm({ onConfirm, onCancel, loading, error }: { onConfirm: (passphrase: string) => void; onCancel: () => void; loading: boolean; error: unknown }) {
  const { t } = useTranslation();
  const [understood, setUnderstood] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  return (
    <div className="space-y-4">
      <Alert tone="warning">{t("backup.restoreWarning")}</Alert>
      <Field label={t("backup.restorePassphrase")} hint={t("backup.restorePassphraseHint")}>
        <Input type="password" autoComplete="off" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} />
      </Field>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />
        {t("backup.restoreUnderstood")}
      </label>
      {!!error && <Alert tone="danger">{errorMessage(t, error, "backup")}</Alert>}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button variant="danger" disabled={!understood} loading={loading} onClick={() => onConfirm(passphrase)}>
          <ArchiveRestore className="h-4 w-4" />
          {t("backup.restore")}
        </Button>
      </div>
    </div>
  );
}

function BackupsDialog({ target, onClose, onJob }: { target: BackupTarget; onClose: () => void; onJob: (id: number) => void }) {
  const { t, i18n } = useTranslation();
  const [restoring, setRestoring] = useState<BackupItem | null>(null);
  const list = useQuery({
    queryKey: ["backups", target.id],
    queryFn: () => api<{ items: BackupItem[] }>(`/backup/targets/${target.id}/backups`),
  });
  const restore = useMutation({
    mutationFn: ({ name, passphrase }: { name: string; passphrase: string }) =>
      api<Job>("/backup/restore", { method: "POST", body: { target_id: target.id, name, passphrase: passphrase || null, confirm: true } }),
    onSuccess: (job) => {
      onClose();
      onJob(job.id);
    },
  });

  return (
    <Dialog open onClose={onClose} title={restoring ? t("backup.restoreTitle", { name: restoring.name }) : t("backup.backupsOn", { name: target.name })} xl>
      {restoring ? (
        <RestoreConfirm
          loading={restore.isPending}
          error={restore.error}
          onCancel={() => setRestoring(null)}
          onConfirm={(passphrase) => restore.mutate({ name: restoring.name, passphrase })}
        />
      ) : (
        <div className="space-y-4">
          {list.isLoading && <div className="py-8 text-center text-sm text-muted">{t("common.loading")}</div>}
          {list.isError && <Alert tone="danger">{errorMessage(t, list.error, "backup")}</Alert>}
          {list.data && !list.data.items.length && <div className="py-8 text-center text-sm text-muted">{t("backup.noBackups")}</div>}
          {!!list.data?.items.length && (
            <div className="max-h-[28rem] overflow-y-auto rounded-md border border-line">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface text-left text-xs uppercase tracking-wider text-muted">
                  <tr>
                    <th className="px-4 py-2">{t("backup.date")}</th>
                    <th className="px-4 py-2">{t("backup.type")}</th>
                    <th className="px-4 py-2 text-right">{t("backup.size")}</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {list.data.items.map((item) => (
                    <tr key={item.name}>
                      <td className="px-4 py-2">
                        <div className="font-semibold">{formatDate(item.created_at, i18n.language)}</div>
                        <div className="font-mono text-[11px] text-muted">{item.name}</div>
                      </td>
                      <td className="px-4 py-2">
                        <Badge tone={item.kind === "full" ? "brand" : "neutral"}>{t(`backup.kinds.${item.kind}`)}</Badge>
                        {!item.restorable && (
                          <Badge tone="danger" className="ml-1">
                            {t("backup.incomplete")}
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs">{formatSize(item.size)}</td>
                      <td className="px-4 py-2">
                        <div className="flex justify-end gap-1">
                          <a
                            href={`/api/backup/targets/${target.id}/backups/${encodeURIComponent(item.name)}`}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface hover:text-ink"
                            title={t("backup.download")}
                            aria-label={t("backup.download")}
                          >
                            <Download className="h-4 w-4" />
                          </a>
                          <Button variant="outline" size="sm" disabled={!item.restorable} onClick={() => setRestoring(item)}>
                            <ArchiveRestore className="h-4 w-4" />
                            {t("backup.restore")}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-muted">{t("backup.chainHint")}</p>
        </div>
      )}
    </Dialog>
  );
}

// ---------------------------------------------------------------- settings

const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

function ScheduleEditor({ kind, value, next, onChange }: { kind: "full" | "incremental"; value: BackupSchedule; next: string | null; onChange: (v: BackupSchedule) => void }) {
  const { t, i18n } = useTranslation();
  const set = <K extends keyof BackupSchedule>(k: K, v: BackupSchedule[K]) => onChange({ ...value, [k]: v });
  const weekday = (d: number) => new Date(2026, 9, 19 + d).toLocaleDateString(i18n.language === "nl" ? "nl-NL" : "en-GB", { weekday: "long" });
  return (
    <div className="rounded-lg border border-line p-4">
      <Switch checked={value.enabled} onChange={(v) => set("enabled", v)} label={t(`backup.schedule.${kind}`)} description={t(`backup.schedule.${kind}Hint`)} />
      {value.enabled && (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Field label={t("backup.schedule.frequency")}>
            <Select value={value.frequency} onChange={(e) => set("frequency", e.target.value as BackupSchedule["frequency"])}>
              {(["hourly", "daily", "weekly", "monthly"] as const).map((f) => (
                <option key={f} value={f}>
                  {t(`backup.schedule.${f}`)}
                </option>
              ))}
            </Select>
          </Field>
          {value.frequency === "weekly" && (
            <Field label={t("backup.schedule.weekday")}>
              <Select value={value.weekday} onChange={(e) => set("weekday", Number(e.target.value))}>
                {WEEKDAYS.map((d) => (
                  <option key={d} value={d}>
                    {weekday(d)}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {value.frequency === "monthly" && (
            <Field label={t("backup.schedule.monthday")}>
              <Select value={value.monthday} onChange={(e) => set("monthday", Number(e.target.value))}>
                {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {value.frequency === "hourly" ? (
            <Field label={t("backup.schedule.minute")}>
              <Select value={value.time.slice(3)} onChange={(e) => set("time", `00:${e.target.value}`)}>
                {["00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"].map((m) => (
                  <option key={m} value={m}>
                    :{m}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <Field label={t("backup.schedule.time")}>
              <Input type="time" value={value.time} onChange={(e) => set("time", e.target.value || "02:00")} />
            </Field>
          )}
          {next && <div className="text-xs text-muted sm:col-span-3">{t("backup.schedule.next", { date: formatDate(next, i18n.language) })}</div>}
        </div>
      )}
    </div>
  );
}

function SettingsCards({ settings }: { settings: BackupSettings }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [form, setForm] = useState(settings);
  const [passphrase, setPassphrase] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => setForm(settings), [settings]);
  const set = <K extends keyof BackupSettings>(k: K, v: BackupSettings[K]) => {
    setSaved(false);
    setForm((f) => ({ ...f, [k]: v }));
  };
  const save = useMutation({
    mutationFn: () =>
      api<BackupSettings>("/backup/settings", {
        method: "PUT",
        body: {
          passphrase: passphrase || null,
          keep_full: form.keep_full,
          schedule_full: form.schedule_full,
          schedule_incremental: form.schedule_incremental,
          notify_email: form.notify_email,
          notify_on: form.notify_on,
        },
      }),
    onSuccess: (data) => {
      qc.setQueryData(["backup-settings"], data);
      setPassphrase("");
      setShowPass(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });
  const generate = useMutation({
    mutationFn: () => api<{ passphrase: string }>("/backup/settings/generate-passphrase", { method: "POST" }),
    onSuccess: (d) => {
      setPassphrase(d.passphrase);
      setShowPass(true);
    },
  });
  const newKey = useMutation({
    mutationFn: () => api<{ ssh_public_key: string }>("/backup/settings/ssh-key", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backup-settings"] }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-6">
      <Card>
        <CardHeader
          title={t("backup.encryption")}
          description={t("backup.encryptionHint")}
          action={form.passphrase_set ? <Badge tone="success">{t("common.configured")}</Badge> : <Badge tone="warning">{t("backup.notSet")}</Badge>}
        />
        <CardBody className="space-y-4">
          <Field label={form.passphrase_set ? t("backup.newPassphrase") : t("backup.passphrase")} hint={form.passphrase_set ? t("backup.passphraseChangeHint") : t("backup.passphraseHint")}>
            <div className="flex gap-2">
              <Input
                type={showPass ? "text" : "password"}
                autoComplete="new-password"
                value={passphrase}
                minLength={12}
                onChange={(e) => setPassphrase(e.target.value)}
                placeholder={form.passphrase_set ? "••••••••••••" : ""}
                className="font-mono"
              />
              <Button type="button" variant="outline" loading={generate.isPending} onClick={() => generate.mutate()} title={t("backup.generate")}>
                <Wand2 className="h-4 w-4" />
                <span className="hidden sm:inline">{t("backup.generate")}</span>
              </Button>
            </div>
          </Field>
          {passphrase && showPass && (
            <div className="flex items-center gap-2">
              <CopyButton value={passphrase} />
              <span className="text-xs text-muted">{t("backup.storeSafely")}</span>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title={t("backup.scheduleTitle")} description={t("backup.scheduleHint")} />
        <CardBody className="space-y-4">
          <ScheduleEditor kind="full" value={form.schedule_full} next={form.next_runs.full} onChange={(v) => set("schedule_full", v)} />
          <ScheduleEditor kind="incremental" value={form.schedule_incremental} next={form.next_runs.incremental} onChange={(v) => set("schedule_incremental", v)} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title={t("backup.retentionTitle")} />
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <Field label={t("backup.keepFull")} hint={t("backup.keepFullHint")} className="sm:col-span-2">
            <Input type="number" min={1} max={100} value={form.keep_full} onChange={(e) => set("keep_full", Number(e.target.value))} className="block w-28" />
          </Field>
          <Field label={t("backup.notifyEmail")} hint={t("backup.notifyHint")}>
            <Input type="email" value={form.notify_email} onChange={(e) => set("notify_email", e.target.value.trim())} placeholder="it@example.com" />
          </Field>
          <Field label={t("backup.notifyOn")}>
            <Select value={form.notify_on} onChange={(e) => set("notify_on", e.target.value as BackupSettings["notify_on"])}>
              <option value="failure">{t("backup.notify.failure")}</option>
              <option value="always">{t("backup.notify.always")}</option>
              <option value="never">{t("backup.notify.never")}</option>
            </Select>
          </Field>
        </CardBody>
      </Card>

      {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "backup")}</Alert>}
      <div className="flex items-center justify-end gap-3">
        {saved && <Badge tone="success">{t("common.saved")}</Badge>}
        <Button type="submit" loading={save.isPending}>
          {t("common.save")}
        </Button>
      </div>

      <Card>
        <CardHeader
          title={t("backup.sshKeyTitle")}
          description={t("backup.sshKeyHelp")}
          action={
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="whitespace-nowrap"
              loading={newKey.isPending}
              onClick={() => window.confirm(t("backup.newSshKeyConfirm")) && newKey.mutate()}
            >
              <RefreshCw className="h-4 w-4" />
              {t("backup.newSshKey")}
            </Button>
          }
        />
        <CardBody className="space-y-2">
          <textarea readOnly value={settings.ssh_public_key} className="h-20 w-full resize-none rounded-md border border-line bg-surface p-2 font-mono text-xs" onFocus={(e) => e.target.select()} />
          <CopyButton value={settings.ssh_public_key} />
        </CardBody>
      </Card>
    </form>
  );
}

function UploadRestore({ onJob }: { onJob: (id: number) => void }) {
  const { t } = useTranslation();
  const [files, setFiles] = useState<File[]>([]);
  const [confirming, setConfirming] = useState(false);
  const restore = useMutation({
    mutationFn: (passphrase: string) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      form.append("passphrase", passphrase);
      form.append("confirm", "true");
      return api<Job>("/backup/restore/upload", { form });
    },
    onSuccess: (job) => {
      setConfirming(false);
      setFiles([]);
      onJob(job.id);
    },
  });
  return (
    <Card>
      <CardHeader title={t("backup.uploadTitle")} description={t("backup.uploadHint")} />
      <CardBody className="space-y-4">
        <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-line px-4 py-6 text-center text-sm text-muted hover:border-lucht">
          <Upload className="h-5 w-5" />
          <span>{files.length ? files.map((f) => f.name).join(", ") : t("backup.chooseFiles")}</span>
          <input type="file" multiple accept=".lprbak" className="hidden" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
        </label>
        {!confirming ? (
          <Button variant="outline" className="w-full" disabled={!files.length} onClick={() => setConfirming(true)}>
            <ArchiveRestore className="h-4 w-4" />
            {t("backup.restore")}
          </Button>
        ) : (
          <RestoreConfirm loading={restore.isPending} error={restore.error} onCancel={() => setConfirming(false)} onConfirm={(p) => restore.mutate(p)} />
        )}
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------- page

function TargetStatus({ target }: { target: BackupTarget }) {
  const { t } = useTranslation();
  if (!target.is_enabled) return <Badge>{t("common.inactive")}</Badge>;
  if (target.last_status === "ok") return <Badge tone="success">{t("backup.statusOk")}</Badge>;
  if (target.last_status === "failed") return <Badge tone="danger">{t("backup.statusFailed")}</Badge>;
  return <Badge tone="warning">{t("backup.statusNone")}</Badge>;
}

export function BackupPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<BackupTarget | "new" | null>(null);
  const [browsing, setBrowsing] = useState<BackupTarget | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const settings = useQuery({ queryKey: ["backup-settings"], queryFn: () => api<BackupSettings>("/backup/settings") });
  const targets = useQuery({ queryKey: ["backup-targets"], queryFn: () => api<BackupTarget[]>("/backup/targets") });
  const run = useMutation({
    mutationFn: (kind: "full" | "incremental") => api<Job>("/backup/run", { method: "POST", body: { kind } }),
    onSuccess: (job) => setJobId(job.id),
  });
  const remove = useMutation({
    mutationFn: (target: BackupTarget) => api(`/backup/targets/${target.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backup-targets"] }),
  });
  const ready = !!settings.data?.passphrase_set && !!targets.data?.some((x) => x.is_enabled);

  return (
    <>
      <PageHeader
        title={t("backup.title")}
        description={t("backup.description")}
        action={
          <div className="flex gap-2">
            <Button variant="outline" disabled={!ready} loading={run.isPending && run.variables === "incremental"} onClick={() => run.mutate("incremental")}>
              <DatabaseBackup className="h-4 w-4" />
              {t("backup.runIncremental")}
            </Button>
            <Button disabled={!ready} loading={run.isPending && run.variables === "full"} onClick={() => run.mutate("full")}>
              <HardDrive className="h-4 w-4" />
              {t("backup.runFull")}
            </Button>
          </div>
        }
      />
      {settings.data && !settings.data.passphrase_set && (
        <div className="mb-6">
          <Alert tone="warning">{t("backup.needPassphrase")}</Alert>
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title={t("backup.targets")}
              description={t("backup.targetsHint")}
              action={
                <Button size="sm" onClick={() => setEditing("new")}>
                  <Plus className="h-4 w-4" />
                  {t("backup.addTarget")}
                </Button>
              }
            />
            {targets.data && !targets.data.length && (
              <CardBody className="flex flex-col items-center py-10 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-lucht/20 text-nacht dark:text-lucht">
                  <HardDrive className="h-6 w-6" />
                </div>
                <p className="mt-3 max-w-md text-sm text-muted">{t("backup.noTargets")}</p>
                <Button variant="accent" className="mt-4" onClick={() => setEditing("new")}>
                  <Plus className="h-4 w-4" />
                  {t("backup.addTarget")}
                </Button>
              </CardBody>
            )}
            <ul className="divide-y divide-line">
              {targets.data?.map((target) => (
                <li key={target.id} className="flex flex-wrap items-center gap-3 px-6 py-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-lucht/20 text-nacht dark:text-lucht">
                    <HardDrive className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-bold">{target.name}</span>
                      <Badge>{t(`backup.protocols.${target.protocol}`)}</Badge>
                      <TargetStatus target={target} />
                    </div>
                    <div className="truncate font-mono text-xs text-muted">
                      {target.username ? `${target.username}@` : ""}
                      {target.host}:{target.port}/{target.remote_path}
                    </div>
                    <div className="mt-1 flex items-center gap-1 text-xs text-muted">
                      {target.last_status === "ok" && <CheckCircle2 className="h-3.5 w-3.5 text-online" />}
                      {target.last_status === "failed" && <XCircle className="h-3.5 w-3.5 text-offline" />}
                      {t("backup.lastBackup")}: {target.last_backup_at ? formatDate(target.last_backup_at, i18n.language) : t("common.never")}
                    </div>
                    {target.last_status === "failed" && target.last_message && (
                      <p className="mt-2 rounded-md bg-offline/10 px-3 py-2 text-xs text-offline">{target.last_message}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button variant="outline" size="sm" onClick={() => setBrowsing(target)}>
                      <FolderOpen className="h-4 w-4" />
                      {t("backup.browse")}
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setEditing(target)} aria-label={t("common.edit")}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("common.delete")}
                      onClick={() => window.confirm(t("backup.confirmDelete", { name: target.name })) && remove.mutate(target)}
                    >
                      <Trash2 className="h-4 w-4 text-offline" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
          {settings.data && <SettingsCards settings={settings.data} />}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title={t("backup.howTitle")} />
            <CardBody>
              <ul className="space-y-3 text-sm">
                {(t("backup.how", { returnObjects: true }) as string[]).map((line, i) => (
                  <li key={i} className="flex gap-3">
                    <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                    <span className="text-muted">{line}</span>
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>
          <UploadRestore onJob={setJobId} />
        </div>
      </div>
      {editing !== null && settings.data && <TargetDialog target={editing} sshPublicKey={settings.data.ssh_public_key} onClose={() => setEditing(null)} />}
      {browsing && <BackupsDialog target={browsing} onClose={() => setBrowsing(null)} onJob={setJobId} />}
      <JobDialog
        jobId={jobId}
        onClose={() => setJobId(null)}
        onFinished={(job) => {
          if (job.kind === "restore") {
            qc.invalidateQueries();
          } else {
            qc.invalidateQueries({ queryKey: ["backup-targets"] });
            qc.invalidateQueries({ queryKey: ["backups"] });
          }
        }}
      />
    </>
  );
}
