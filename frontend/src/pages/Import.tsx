import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, FileUp, Layers, Play, Search, Upload, X } from "lucide-react";
import { api, type Console, type ImportField, type ImportPlan, type ImportRow, type Job, type VehicleList } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/form";
import { Alert, Badge, PageHeader } from "@/components/ui/misc";
import { JobDialog } from "@/components/JobDialog";
import { Checkbox, Plate } from "@/components/vehicles";

const FIELDS: ImportField[] = ["plate", "department", "location", "group_name", "description"];
const REQUIRED: ImportField[] = ["plate", "department"];

interface Parsed {
  filename: string;
  headers: string[];
  rows: Record<string, string>[];
  mapping: Partial<Record<ImportField, string>>;
  defaults: Partial<Record<ImportField, string>>;
}

interface WorkRow extends ImportRow {
  id: number;
  include: boolean;
}

function convert(parsed: Parsed, mapping: Parsed["mapping"], defaults: Parsed["defaults"]): WorkRow[] {
  return parsed.rows.map((raw, i) => {
    const pick = (f: ImportField) => ((mapping[f] ? raw[mapping[f]!] : "") || defaults[f] || "").trim();
    return { id: i, include: true, plate: pick("plate"), department: pick("department"), location: pick("location"), group_name: pick("group_name"), description: pick("description") };
  });
}

function Steps({ step }: { step: number }) {
  const { t } = useTranslation();
  const names = t("import.steps", { returnObjects: true }) as string[];
  return (
    <ol className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {names.map((name, i) => (
        <li
          key={name}
          className={cn(
            "flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold",
            i === step ? "border-nacht bg-raised text-ink dark:border-lucht" : i < step ? "border-line bg-raised text-muted" : "border-transparent text-muted",
          )}
        >
          <span
            className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold",
              i < step ? "bg-online text-white" : i === step ? "bg-nacht text-white dark:bg-lucht dark:text-nacht" : "bg-surface ring-1 ring-line",
            )}
          >
            {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}
          </span>
          <span className="truncate">{name}</span>
        </li>
      ))}
    </ol>
  );
}

function UploadStep({ onParsed }: { onParsed: (p: Parsed) => void }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const parse = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<Parsed>("/import/parse", { form });
    },
    onSuccess: onParsed,
  });
  const pick = (files: FileList | null) => files?.[0] && parse.mutate(files[0]);
  return (
    <Card>
      <CardBody className="space-y-4">
        {parse.isError && <Alert tone="danger">{errorMessage(t, parse.error, "import")}</Alert>}
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            pick(e.dataTransfer.files);
          }}
          className={cn(
            "flex w-full flex-col items-center rounded-lg border-2 border-dashed px-6 py-14 text-center transition-colors",
            drag ? "border-lucht bg-lucht/10" : "border-line hover:border-lucht hover:bg-surface",
          )}
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-lucht/20 text-nacht dark:text-lucht">
            <Upload className="h-6 w-6" />
          </div>
          <div className="mt-4 font-semibold">{parse.isPending ? t("common.loading") : t("import.dropTitle")}</div>
          <div className="mt-1 max-w-md text-sm text-muted">{t("import.dropBody")}</div>
        </button>
        <input ref={input} type="file" accept=".csv,text/csv,.txt" className="hidden" onChange={(e) => pick(e.target.files)} />
      </CardBody>
    </Card>
  );
}

function MappingStep({ parsed, mapping, setMapping, defaults, setDefaults }: {
  parsed: Parsed;
  mapping: Parsed["mapping"];
  setMapping: (m: Parsed["mapping"]) => void;
  defaults: Parsed["defaults"];
  setDefaults: (d: Parsed["defaults"]) => void;
}) {
  const { t } = useTranslation();
  const sample = convert({ ...parsed, rows: parsed.rows.slice(0, 5) }, mapping, defaults);
  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
      <Card>
        <CardHeader title={t("import.mappingTitle")} description={t("import.mappingBody", { file: parsed.filename, count: parsed.rows.length })} />
        <CardBody className="space-y-4">
          {FIELDS.map((f) => (
            <div key={f} className="space-y-2">
              <Field label={<>{t(`import.fields.${f}`)}{REQUIRED.includes(f) && <span className="text-accent-text"> *</span>}</>} hint={t(`import.fieldHints.${f}`)}>
                <Select value={mapping[f] ?? ""} onChange={(e) => setMapping({ ...mapping, [f]: e.target.value || undefined })}>
                  <option value="">{t("import.noColumn")}</option>
                  {parsed.headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </Select>
              </Field>
              {(f === "department" || f === "location") && (
                <Input
                  placeholder={t("import.defaultPlaceholder")}
                  value={defaults[f] ?? ""}
                  onChange={(e) => setDefaults({ ...defaults, [f]: e.target.value })}
                  aria-label={t("import.defaultPlaceholder")}
                />
              )}
            </div>
          ))}
        </CardBody>
      </Card>
      <Card className="overflow-hidden">
        <CardHeader title={t("import.sampleTitle")} description={t("import.sampleBody")} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-xs font-medium uppercase tracking-wide text-muted">
              <tr>
                {FIELDS.map((f) => (
                  <th key={f} className="px-4 py-3">
                    {t(`import.fields.${f}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {sample.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2 font-mono">{r.plate || "–"}</td>
                  <td className="px-4 py-2">{r.department || <span className="text-offline">–</span>}</td>
                  <td className="px-4 py-2">{r.location || "–"}</td>
                  <td className="px-4 py-2 text-muted">{r.group_name || [r.department, r.location].filter(Boolean).join(" ") || "–"}</td>
                  <td className="px-4 py-2 text-muted">{r.description || "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

const STATUS_TONE = { new: "brand", changed: "warning", unchanged: "neutral", invalid: "danger" } as const;

function ReviewStep({ rows, setRows, plan }: { rows: WorkRow[]; setRows: (r: WorkRow[]) => void; plan?: ImportPlan }) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [groupValue, setGroupValue] = useState("");
  const [bulkField, setBulkField] = useState<"group_name" | "department" | "location">("group_name");

  const included = rows.filter((r) => r.include);
  const planned = useMemo(() => new Map(included.map((r, i) => [r.id, plan?.rows[i]])), [included, plan]);
  const locations = [...new Set(rows.map((r) => r.location).filter(Boolean))].sort();
  const departments = [...new Set(rows.map((r) => r.department).filter(Boolean))].sort();
  const visible = rows.filter((r) => {
    const p = planned.get(r.id);
    if (location && r.location !== location) return false;
    if (department && r.department !== department) return false;
    if (status === "excluded") return !r.include;
    if (status && (!r.include || p?.status !== status)) return false;
    if (q && !`${r.plate} ${r.description} ${r.group_name}`.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });
  const chosen = visible.filter((r) => selected.has(r.id)).map((r) => r.id);
  const patch = (ids: number[], change: Partial<WorkRow>) => {
    const set = new Set(ids);
    setRows(rows.map((r) => (set.has(r.id) ? { ...r, ...change } : r)));
  };
  const groups = useMemo(() => {
    const counts = new Map<string, number>();
    plan?.rows.forEach((r) => r.status !== "invalid" && counts.set(r.group_name, (counts.get(r.group_name) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [plan]);

  return (
    <div className="space-y-4">
      {plan && (
        <div className="grid gap-3 sm:grid-cols-5">
          {(["new", "changed", "unchanged", "invalid"] as const).map((s) => (
            <button key={s} onClick={() => setStatus(status === s ? "" : s)} className={cn("rounded-lg border bg-raised p-4 text-left", status === s ? "border-nacht dark:border-lucht" : "border-line")}>
              <div className="text-2xl font-bold">{plan.summary[s]}</div>
              <div className="text-sm text-muted">{t(`import.status.${s}`)}</div>
            </button>
          ))}
          <button onClick={() => setStatus(status === "excluded" ? "" : "excluded")} className={cn("rounded-lg border bg-raised p-4 text-left", status === "excluded" ? "border-nacht dark:border-lucht" : "border-line")}>
            <div className="text-2xl font-bold">{rows.length - included.length}</div>
            <div className="text-sm text-muted">{t("import.status.excluded")}</div>
          </button>
        </div>
      )}
      {!!groups.length && (
        <Card>
          <CardBody className="flex flex-wrap items-center gap-2 py-3">
            <Layers className="h-4 w-4 text-muted" />
            <span className="mr-1 text-sm font-semibold">{t("import.groups")}</span>
            {groups.map(([g, n]) => (
              <Badge key={g} tone="brand">
                {g || t("import.noGroup")} · {n}
              </Badge>
            ))}
          </CardBody>
        </Card>
      )}
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line p-4">
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input className="pl-9" placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select className="w-auto" value={location} onChange={(e) => setLocation(e.target.value)} aria-label={t("import.fields.location")}>
            <option value="">{t("vehicles.allLocations")}</option>
            {locations.map((l) => <option key={l}>{l}</option>)}
          </Select>
          <Select className="w-auto" value={department} onChange={(e) => setDepartment(e.target.value)} aria-label={t("import.fields.department")}>
            <option value="">{t("vehicles.allDepartments")}</option>
            {departments.map((l) => <option key={l}>{l}</option>)}
          </Select>
        </div>
        {chosen.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-nacht px-4 py-2 text-white dark:bg-lucht/15">
            <span className="text-sm font-semibold">{t("vehicles.selected", { count: chosen.length })}</span>
            <div className="flex-1" />
            <select
              className="h-8 rounded-md bg-white/10 px-2 text-sm text-white [&>option]:text-nacht"
              value={bulkField}
              onChange={(e) => setBulkField(e.target.value as typeof bulkField)}
              aria-label={t("import.bulkField")}
            >
              <option value="group_name">{t("import.assignGroup")}</option>
              <option value="department">{t("import.setDepartment")}</option>
              <option value="location">{t("import.setLocation")}</option>
            </select>
            <input
              list="dl-import-groups"
              className="h-8 w-56 rounded-md bg-white px-2 text-sm text-nacht"
              placeholder={bulkField === "group_name" ? "Netwerktransport Wognum" : ""}
              value={groupValue}
              onChange={(e) => setGroupValue(e.target.value)}
            />
            <datalist id="dl-import-groups">{groups.map(([g]) => <option key={g} value={g} />)}</datalist>
            <Button size="sm" variant="accent" disabled={!groupValue.trim()} onClick={() => { patch(chosen, { [bulkField]: groupValue.trim() }); setGroupValue(""); }}>
              {t("import.apply")}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => patch(chosen, { include: !rows.find((r) => r.id === chosen[0])?.include })}>
              {rows.find((r) => r.id === chosen[0])?.include ? t("import.exclude") : t("import.include")}
            </Button>
          </div>
        )}
        <div className="max-h-[60vh] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-surface text-left text-xs font-medium uppercase tracking-wide text-muted">
              <tr>
                <th className="w-10 px-4 py-3">
                  <Checkbox
                    checked={visible.length > 0 && chosen.length === visible.length}
                    indeterminate={chosen.length > 0}
                    onChange={(on) => setSelected(on ? new Set(visible.map((r) => r.id)) : new Set())}
                  />
                </th>
                <th className="px-4 py-3">#</th>
                <th className="px-4 py-3">{t("import.fields.plate")}</th>
                <th className="px-4 py-3">{t("import.fields.department")}</th>
                <th className="px-4 py-3">{t("import.fields.location")}</th>
                <th className="px-4 py-3">{t("import.fields.group_name")}</th>
                <th className="px-4 py-3">{t("import.result")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {visible.slice(0, 1000).map((r) => {
                const p = planned.get(r.id);
                return (
                  <tr key={r.id} className={cn(!r.include && "opacity-50", selected.has(r.id) && "bg-lucht/10")}>
                    <td className="px-4 py-2">
                      <Checkbox
                        checked={selected.has(r.id)}
                        onChange={(on) =>
                          setSelected((s) => {
                            const n = new Set(s);
                            if (on) n.add(r.id);
                            else n.delete(r.id);
                            return n;
                          })
                        }
                      />
                    </td>
                    <td className="px-4 py-2 text-xs text-muted">{r.id + 1}</td>
                    <td className="px-4 py-2">{p?.plate ? <Plate value={p.plate} /> : <span className="font-mono">{r.plate || "–"}</span>}</td>
                    <td className="px-4 py-2">{r.department || "–"}</td>
                    <td className="px-4 py-2">{r.location || "–"}</td>
                    <td className="px-4 py-2 font-medium">{p?.group_name || r.group_name || "–"}</td>
                    <td className="px-4 py-2">
                      {!r.include ? (
                        <Badge>{t("import.status.excluded")}</Badge>
                      ) : p ? (
                        <Badge tone={STATUS_TONE[p.status]}>{p.error ? t(`import.errors.${p.error}`) : t(`import.status.${p.status}`)}</Badge>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="border-t border-line px-4 py-3 text-sm text-muted">
          {t("import.visible", { count: visible.length, total: rows.length })}
          {visible.length > 1000 && ` · ${t("import.firstThousand")}`}
        </div>
      </Card>
    </div>
  );
}

function ConfirmStep({ plan, consoleIds, setConsoleIds, mode, setMode, consoles }: {
  plan?: ImportPlan;
  consoleIds: number[];
  setConsoleIds: (v: number[]) => void;
  mode: "upsert" | "full";
  setMode: (m: "upsert" | "full") => void;
  consoles: VehicleList["consoles"];
}) {
  const { t } = useTranslation();
  const valid = plan ? plan.summary.total - plan.summary.invalid : 0;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title={t("import.consolesTitle")} description={t("import.consolesBody")} />
        <CardBody className="space-y-2">
          {!consoles.filter((c) => c.is_active).length && <Alert tone="warning">{t("import.noConsoles")}</Alert>}
          {consoles
            .filter((c) => c.is_active)
            .map((c) => {
              const p = plan?.consoles.find((x) => x.id === c.id);
              return (
                <label key={c.id} className="flex cursor-pointer items-center gap-3 rounded-md border border-line px-3 py-3 text-sm hover:bg-surface">
                  <Checkbox checked={consoleIds.includes(c.id)} onChange={(on) => setConsoleIds(on ? [...consoleIds, c.id] : consoleIds.filter((x) => x !== c.id))} />
                  <div className="flex-1">
                    <div className="font-semibold">{c.name}</div>
                    <div className="text-xs text-muted">{p?.scanned_at ? t("import.basedOnScan") : t("import.notScanned")}</div>
                  </div>
                  {p && (
                    <div className="text-right text-xs">
                      <div className="font-semibold text-ink">{t("import.toAdd", { count: p.add })}</div>
                      <div className="text-muted">{t("import.alreadyPresent", { count: p.present })}</div>
                      {mode === "full" && p.remove > 0 && <div className="text-offline">{t("import.toRemove", { count: p.remove })}</div>}
                    </div>
                  )}
                </label>
              );
            })}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title={t("import.summaryTitle")} />
        <CardBody className="space-y-5">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-md bg-surface p-3">
              <dt className="text-muted">{t("import.toImport")}</dt>
              <dd className="text-2xl font-bold">{valid}</dd>
            </div>
            <div className="rounded-md bg-surface p-3">
              <dt className="text-muted">{t("import.groups")}</dt>
              <dd className="text-2xl font-bold">{plan?.summary.groups.length ?? 0}</dd>
            </div>
          </dl>
          <div>
            <div className="mb-2 text-sm font-semibold">{t("import.mode")}</div>
            <div className="grid gap-2">
              {(["upsert", "full"] as const).map((m) => (
                <label key={m} className={cn("flex cursor-pointer gap-3 rounded-md border px-3 py-3 text-sm", mode === m ? "border-nacht dark:border-lucht" : "border-line")}>
                  <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} className="mt-0.5" />
                  <div>
                    <div className="font-semibold">{t(`import.modes.${m}`)}</div>
                    <div className="text-muted">{t(`import.modes.${m}Hint`)}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
          {mode === "full" && !!plan?.remove.length && (
            <Alert tone="warning">
              <div className="font-semibold">{t("import.removeWarning", { count: plan.remove.length })}</div>
              <div className="mt-1 font-mono text-xs">{plan.remove.slice(0, 30).join(", ")}{plan.remove.length > 30 ? " …" : ""}</div>
            </Alert>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

export function ImportPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [mapping, setMapping] = useState<Parsed["mapping"]>({});
  const [defaults, setDefaults] = useState<Parsed["defaults"]>({});
  const [rows, setRows] = useState<WorkRow[]>([]);
  const [consoleIds, setConsoleIds] = useState<number[]>([]);
  const [mode, setMode] = useState<"upsert" | "full">("upsert");
  const [jobId, setJobId] = useState<number | null>(null);
  const [finished, setFinished] = useState<Job | null>(null);

  const consoles = useQuery({ queryKey: ["consoles"], queryFn: () => api<Console[]>("/consoles") });
  useEffect(() => {
    if (consoles.data) setConsoleIds(consoles.data.filter((c) => c.is_active).map((c) => c.id));
  }, [consoles.data]);

  const included = useMemo(() => rows.filter((r) => r.include).map(({ id: _i, include: _x, ...r }) => r), [rows]);
  const [debounced, setDebounced] = useState(included);
  useEffect(() => {
    const h = setTimeout(() => setDebounced(included), 300);
    return () => clearTimeout(h);
  }, [included]);
  const plan = useQuery({
    queryKey: ["import-plan", debounced, consoleIds, mode],
    queryFn: () => api<ImportPlan>("/import/preview", { method: "POST", body: { rows: debounced, console_ids: consoleIds, mode } }),
    enabled: step >= 2 && debounced.length > 0,
    placeholderData: keepPreviousData,
  });
  const run = useMutation({
    mutationFn: () => api<Job>("/import/run", { method: "POST", body: { rows: included, console_ids: consoleIds, mode } }),
    onSuccess: (job) => setJobId(job.id),
  });

  const mappingOk = REQUIRED.every((f) => mapping[f] || (f === "department" && defaults.department?.trim()));
  const next = () => {
    if (step === 1 && parsed) {
      api("/import/mapping", { method: "PUT", body: { mapping, defaults } }).catch(() => undefined);
      setRows(convert(parsed, mapping, defaults));
    }
    setStep(step + 1);
  };
  const reset = () => {
    setStep(0);
    setParsed(null);
    setRows([]);
    setFinished(null);
    setMode("upsert");
  };

  return (
    <>
      <PageHeader title={t("import.title")} description={t("import.description")} />
      <Steps step={step} />
      {finished ? (
        <Card className="flex flex-col items-center px-6 py-14 text-center">
          <div className={cn("flex h-12 w-12 items-center justify-center rounded-full", finished.failed ? "bg-warning/15 text-warning" : "bg-online/15 text-online")}>
            {finished.failed ? <X className="h-6 w-6" /> : <Check className="h-6 w-6" />}
          </div>
          <h2 className="mt-4 font-semibold">{t(finished.failed ? "import.doneWithErrors" : "import.done")}</h2>
          <p className="mt-1 max-w-md text-sm text-muted">{t("import.doneBody", { succeeded: finished.succeeded, failed: finished.failed })}</p>
          <div className="mt-5 flex gap-2">
            <Button variant="outline" onClick={() => setJobId(finished.id)}>
              {t("jobs.report")}
            </Button>
            <Link to="/vehicles">
              <Button>{t("import.toVehicles")}</Button>
            </Link>
            <Button variant="ghost" onClick={reset}>
              <FileUp className="h-4 w-4" />
              {t("import.another")}
            </Button>
          </div>
        </Card>
      ) : (
        <>
          {step === 0 && (
            <UploadStep
              onParsed={(p) => {
                setParsed(p);
                setMapping(p.mapping);
                setDefaults(p.defaults);
                setStep(1);
              }}
            />
          )}
          {step === 1 && parsed && <MappingStep parsed={parsed} mapping={mapping} setMapping={setMapping} defaults={defaults} setDefaults={setDefaults} />}
          {step === 2 && <ReviewStep rows={rows} setRows={setRows} plan={plan.data} />}
          {step === 3 && <ConfirmStep plan={plan.data} consoleIds={consoleIds} setConsoleIds={setConsoleIds} mode={mode} setMode={setMode} consoles={consoles.data ?? []} />}
          {plan.isError && (
            <div className="mt-4">
              <Alert tone="danger">{errorMessage(t, plan.error, "import")}</Alert>
            </div>
          )}
          {run.isError && (
            <div className="mt-4">
              <Alert tone="danger">{errorMessage(t, run.error, "import")}</Alert>
            </div>
          )}
          {step > 0 && (
            <div className="mt-6 flex items-center justify-between">
              <Button variant="outline" onClick={() => (step === 1 ? reset() : setStep(step - 1))}>
                <ArrowLeft className="h-4 w-4" />
                {t("common.previous")}
              </Button>
              {step < 3 ? (
                <Button onClick={next} disabled={(step === 1 && !mappingOk) || (step === 2 && !included.length)}>
                  {t("common.next")}
                  <ArrowRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button variant="accent" loading={run.isPending} disabled={!plan.data || plan.data.summary.total === plan.data.summary.invalid} onClick={() => run.mutate()}>
                  <Play className="h-4 w-4" />
                  {consoleIds.length ? t("import.start", { count: consoleIds.length }) : t("import.startStoreOnly")}
                </Button>
              )}
            </div>
          )}
        </>
      )}
      <JobDialog
        jobId={jobId}
        onClose={() => setJobId(null)}
        onFinished={(job) => {
          setFinished(job);
          qc.invalidateQueries({ queryKey: ["vehicles"] });
          qc.invalidateQueries({ queryKey: ["adopt"] });
        }}
      />
    </>
  );
}
