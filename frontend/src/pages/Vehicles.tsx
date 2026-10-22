import { useMemo, useState, type FormEvent } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Download, Pencil, Plus, RefreshCw, Search, Send, Trash2, Truck, X } from "lucide-react";
import { api, type AdoptCandidate, type Job, type Vehicle, type VehicleList } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Alert, Dialog, PageHeader } from "@/components/ui/misc";
import { JobDialog } from "@/components/JobDialog";
import { Checkbox, Plate, PresenceCell, Tag, useCanEdit } from "@/components/vehicles";

interface Filters {
  departments: string[];
  locations: string[];
  groups: string[];
}

function useFilters() {
  return useQuery({ queryKey: ["vehicles", "filters"], queryFn: () => api<Filters>("/vehicles/filters") });
}

function conventionPreview(department: string, location: string, group: string, plate: string) {
  const g = group.trim() || [department.trim(), location.trim()].filter(Boolean).join(" ");
  return { user: `${department.trim() || "…"} ${plate.trim().toUpperCase() || "…"}`, group: g || "–" };
}

function Datalist({ id, values }: { id: string; values?: string[] }) {
  return (
    <datalist id={id}>
      {values?.map((v) => <option key={v} value={v} />)}
    </datalist>
  );
}

function VehicleDialog({ vehicle, onClose }: { vehicle: Vehicle | "new"; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const filters = useFilters();
  const isNew = vehicle === "new";
  const v = isNew ? null : vehicle;
  const [form, setForm] = useState({
    plate: v?.plate ?? "",
    department: v?.department ?? "",
    location: v?.location ?? "",
    group_name: v?.group_name ?? "",
    description: v?.description ?? "",
  });
  const [groupTouched, setGroupTouched] = useState(!isNew && !!v && v.group_name !== [v.department, v.location].filter(Boolean).join(" "));
  const set = <K extends keyof typeof form>(k: K, val: string) => setForm((f) => ({ ...f, [k]: val }));
  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, group_name: groupTouched ? form.group_name : "" };
      if (isNew) return api("/vehicles", { method: "POST", body });
      const { plate: _p, ...rest } = body;
      return api(`/vehicles/${v!.id}`, { method: "PATCH", body: groupTouched ? rest : { ...rest, group_name: undefined } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vehicles"] });
      onClose();
    },
  });
  const preview = conventionPreview(form.department, form.location, groupTouched ? form.group_name : "", form.plate);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <Dialog open onClose={onClose} title={isNew ? t("vehicles.add") : v!.plate}>
      <form onSubmit={submit} className="space-y-4">
        {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "vehicles")}</Alert>}
        {isNew && (
          <Field label={t("vehicles.plate")} hint={t("vehicles.plateHint")}>
            <Input value={form.plate} onChange={(e) => set("plate", e.target.value)} className="font-mono uppercase" required autoFocus />
          </Field>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("vehicles.department")}>
            <Input list="dl-departments" value={form.department} onChange={(e) => set("department", e.target.value)} placeholder="Netwerktransport" required />
          </Field>
          <Field label={t("vehicles.location")}>
            <Input list="dl-locations" value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="Wognum" />
          </Field>
        </div>
        <Field label={t("vehicles.group")} hint={t("vehicles.groupHint")}>
          <Input
            list="dl-groups"
            value={groupTouched ? form.group_name : preview.group === "–" ? "" : preview.group}
            onChange={(e) => {
              setGroupTouched(true);
              set("group_name", e.target.value);
            }}
          />
        </Field>
        <Field label={t("vehicles.description")}>
          <Input value={form.description} onChange={(e) => set("description", e.target.value)} placeholder="DAF XF" />
        </Field>
        <Datalist id="dl-departments" values={filters.data?.departments} />
        <Datalist id="dl-locations" values={filters.data?.locations} />
        <Datalist id="dl-groups" values={filters.data?.groups} />
        <div className="rounded-md bg-surface px-4 py-3 text-sm">
          <div className="text-xs font-bold uppercase tracking-wide text-muted">{t("vehicles.convention")}</div>
          <div className="mt-1">
            {t("vehicles.conventionUser")}: <span className="font-semibold">{preview.user}</span>
          </div>
          <div>
            {t("vehicles.conventionGroup")}: <span className="font-semibold">{preview.group}</span>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
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

function ConsolePicker({ consoles, value, onChange }: { consoles: VehicleList["consoles"]; value: number[]; onChange: (v: number[]) => void }) {
  return (
    <div className="space-y-2">
      {consoles
        .filter((c) => c.is_active)
        .map((c) => (
          <label key={c.id} className="flex cursor-pointer items-center gap-3 rounded-md border border-line px-3 py-2 text-sm hover:bg-surface">
            <Checkbox checked={value.includes(c.id)} onChange={(on) => onChange(on ? [...value, c.id] : value.filter((x) => x !== c.id))} />
            <span className="flex-1 font-semibold">{c.name}</span>
            <span className="text-xs text-muted">{c.location}</span>
          </label>
        ))}
    </div>
  );
}

function AssignDialog({ ids, consoles, mode, onClose, onJob }: { ids: number[]; consoles: VehicleList["consoles"]; mode: "assign" | "remove"; onClose: () => void; onJob: (id: number) => void }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState(consoles.filter((c) => c.is_active).map((c) => c.id));
  const [deleteVehicles, setDeleteVehicles] = useState(false);
  const run = useMutation({
    mutationFn: () =>
      api<Job>(`/vehicles/${mode}`, {
        method: "POST",
        body: mode === "assign" ? { vehicle_ids: ids, console_ids: selected } : { vehicle_ids: ids, console_ids: selected, delete_vehicles: deleteVehicles },
      }),
    onSuccess: (job) => {
      onClose();
      onJob(job.id);
    },
  });
  return (
    <Dialog open onClose={onClose} title={t(mode === "assign" ? "vehicles.assignTitle" : "vehicles.removeTitle", { count: ids.length })}>
      <div className="space-y-4">
        <p className="text-sm text-muted">{t(mode === "assign" ? "vehicles.assignBody" : "vehicles.removeBody")}</p>
        <ConsolePicker consoles={consoles} value={selected} onChange={setSelected} />
        {mode === "remove" && (
          <Switch checked={deleteVehicles} onChange={setDeleteVehicles} label={t("vehicles.alsoDelete")} description={t("vehicles.alsoDeleteHint")} />
        )}
        {run.isError && <Alert tone="danger">{errorMessage(t, run.error, "vehicles")}</Alert>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button variant={mode === "remove" ? "danger" : "primary"} disabled={!selected.length} loading={run.isPending} onClick={() => run.mutate()}>
            {mode === "assign" ? <Send className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
            {t(mode === "assign" ? "vehicles.assign" : "vehicles.remove")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function BulkEditDialog({ ids, onClose }: { ids: number[]; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const filters = useFilters();
  const [form, setForm] = useState({ department: "", location: "", group_name: "" });
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { vehicle_ids: ids };
      for (const [k, v] of Object.entries(form)) if (v.trim()) body[k] = v.trim();
      return api("/vehicles/bulk-edit", { method: "POST", body });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vehicles"] });
      onClose();
    },
  });
  return (
    <Dialog open onClose={onClose} title={t("vehicles.bulkEditTitle", { count: ids.length })}>
      <div className="space-y-4">
        <p className="text-sm text-muted">{t("vehicles.bulkEditBody")}</p>
        <Field label={t("vehicles.department")}>
          <Input list="dl-departments" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
        </Field>
        <Field label={t("vehicles.location")}>
          <Input list="dl-locations" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
        </Field>
        <Field label={t("vehicles.group")} hint={t("vehicles.bulkGroupHint")}>
          <Input list="dl-groups" value={form.group_name} onChange={(e) => setForm({ ...form, group_name: e.target.value })} />
        </Field>
        <Datalist id="dl-departments" values={filters.data?.departments} />
        <Datalist id="dl-locations" values={filters.data?.locations} />
        <Datalist id="dl-groups" values={filters.data?.groups} />
        {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "vehicles")}</Alert>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button loading={save.isPending} disabled={!Object.values(form).some((v) => v.trim())} onClick={() => save.mutate()}>
            {t("common.save")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function AdoptDialog({ candidates, onClose }: { candidates: AdoptCandidate[]; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [rows, setRows] = useState(() => candidates.map((c) => ({ ...c, selected: !!c.department })));
  const update = (i: number, patch: Partial<(typeof rows)[number]>) => setRows((r) => r.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  const chosen = rows.filter((r) => r.selected && r.department.trim());
  const adopt = useMutation({
    mutationFn: () =>
      api<{ adopted: number }>("/vehicles/adopt", {
        method: "POST",
        body: { items: chosen.map(({ plate, department, location, group_name }) => ({ plate, department, location, group_name })) },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vehicles"] });
      qc.invalidateQueries({ queryKey: ["adopt"] });
      onClose();
    },
  });
  return (
    <Dialog open onClose={onClose} title={t("vehicles.adoptTitle")} xl>
      <div className="space-y-4">
        <p className="text-sm text-muted">{t("vehicles.adoptBody")}</p>
        <div className="max-h-[55vh] overflow-auto rounded-md border border-line">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface text-left text-xs font-medium uppercase tracking-wide text-muted">
              <tr>
                <th className="w-8 px-3 py-2">
                  <Checkbox
                    checked={rows.every((r) => r.selected)}
                    indeterminate={rows.some((r) => r.selected)}
                    onChange={(on) => setRows((r) => r.map((x) => ({ ...x, selected: on })))}
                  />
                </th>
                <th className="px-3 py-2">{t("vehicles.plate")}</th>
                <th className="px-3 py-2">{t("vehicles.accessUser")}</th>
                <th className="px-3 py-2">{t("vehicles.department")}</th>
                <th className="px-3 py-2">{t("vehicles.location")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r, i) => (
                <tr key={r.plate_key} className="align-middle">
                  <td className="px-3 py-2">
                    <Checkbox checked={r.selected} onChange={(on) => update(i, { selected: on })} />
                  </td>
                  <td className="px-3 py-2">
                    <Plate value={r.plate} />
                    <div className="mt-1 text-xs text-muted">{r.consoles.join(", ")}</div>
                  </td>
                  <td className="px-3 py-2">
                    <div>{r.user_name}</div>
                    {!r.follows_convention && <div className="text-xs text-warning">{t("vehicles.noConvention")}</div>}
                  </td>
                  <td className="px-3 py-2">
                    <Input className="h-8" value={r.department} onChange={(e) => update(i, { department: e.target.value, selected: true })} />
                  </td>
                  <td className="px-3 py-2">
                    <Input className="h-8" value={r.location} onChange={(e) => update(i, { location: e.target.value })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {adopt.isError && <Alert tone="danger">{errorMessage(t, adopt.error, "vehicles")}</Alert>}
        <div className="flex items-center justify-end gap-2">
          <span className="mr-auto text-sm text-muted">{t("vehicles.adoptCount", { count: chosen.length })}</span>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!chosen.length} loading={adopt.isPending} onClick={() => adopt.mutate()}>
            <Download className="h-4 w-4" />
            {t("vehicles.adopt")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

type PresenceFilter = "" | "missing" | "complete";

export function VehiclesPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const canEdit = useCanEdit();
  const [q, setQ] = useState("");
  const [department, setDepartment] = useState("");
  const [location, setLocation] = useState("");
  const [group, setGroup] = useState("");
  const [presence, setPresence] = useState<PresenceFilter>("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<Vehicle | "new" | null>(null);
  const [action, setAction] = useState<"assign" | "remove" | "edit" | "adopt" | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);

  const params = new URLSearchParams({ q, department, location, group }).toString();
  const list = useQuery({ queryKey: ["vehicles", "list", params], queryFn: () => api<VehicleList>(`/vehicles?${params}`), placeholderData: keepPreviousData });
  const filters = useFilters();
  const adopt = useQuery({ queryKey: ["adopt"], queryFn: () => api<AdoptCandidate[]>("/vehicles/adopt") });
  const scan = useMutation({
    mutationFn: () => api<Job>("/consoles/scan", { method: "POST", body: { console_ids: null } }),
    onSuccess: (job) => setJobId(job.id),
  });

  const consoles = list.data?.consoles ?? [];
  const active = consoles.filter((c) => c.is_active);
  const items = useMemo(() => {
    const all = list.data?.items ?? [];
    if (!presence) return all;
    return all.filter((v) => {
      const missing = active.some((c) => !v.presence[String(c.id)]);
      return presence === "missing" ? missing : !missing;
    });
  }, [list.data, presence, active]);
  const ids = items.map((v) => v.id);
  const chosen = ids.filter((id) => selected.has(id));
  const toggle = (id: number, on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["vehicles"] });
    qc.invalidateQueries({ queryKey: ["adopt"] });
    qc.invalidateQueries({ queryKey: ["consoles"] });
  };

  return (
    <>
      <PageHeader
        title={t("vehicles.title")}
        description={t("vehicles.intro")}
        action={
          canEdit && (
            <div className="flex gap-2">
              <Button variant="outline" loading={scan.isPending} disabled={!active.length} onClick={() => scan.mutate()}>
                <RefreshCw className="h-4 w-4" />
                {t("vehicles.readConsoles")}
              </Button>
              <Button onClick={() => setEditing("new")}>
                <Plus className="h-4 w-4" />
                {t("vehicles.add")}
              </Button>
            </div>
          )
        }
      />

      {canEdit && !!adopt.data?.length && (
        <div className="mb-4">
          <Alert tone="info">
            <div className="flex flex-wrap items-center gap-3">
              <span className="flex-1">{t("vehicles.adoptBanner", { count: adopt.data.length })}</span>
              <Button size="sm" onClick={() => setAction("adopt")}>
                {t("vehicles.adoptReview")}
              </Button>
            </div>
          </Alert>
        </div>
      )}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line p-4">
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input className="pl-9" placeholder={t("vehicles.searchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select className="w-auto" value={department} onChange={(e) => setDepartment(e.target.value)} aria-label={t("vehicles.department")}>
            <option value="">{t("vehicles.allDepartments")}</option>
            {filters.data?.departments.map((d) => <option key={d}>{d}</option>)}
          </Select>
          <Select className="w-auto" value={location} onChange={(e) => setLocation(e.target.value)} aria-label={t("vehicles.location")}>
            <option value="">{t("vehicles.allLocations")}</option>
            {filters.data?.locations.map((d) => <option key={d}>{d}</option>)}
          </Select>
          <Select className="w-auto" value={group} onChange={(e) => setGroup(e.target.value)} aria-label={t("vehicles.group")}>
            <option value="">{t("vehicles.allGroups")}</option>
            {filters.data?.groups.map((d) => <option key={d}>{d}</option>)}
          </Select>
          <Select className="w-auto" value={presence} onChange={(e) => setPresence(e.target.value as PresenceFilter)} aria-label={t("vehicles.presence")}>
            <option value="">{t("vehicles.presenceAll")}</option>
            <option value="missing">{t("vehicles.presenceMissing")}</option>
            <option value="complete">{t("vehicles.presenceComplete")}</option>
          </Select>
        </div>

        {canEdit && chosen.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-nacht px-4 py-2 text-white dark:bg-lucht/15">
            <span className="text-sm font-semibold">{t("vehicles.selected", { count: chosen.length })}</span>
            <button className="rounded p-1 text-white/70 hover:text-white" onClick={() => setSelected(new Set())} aria-label={t("common.cancel")}>
              <X className="h-4 w-4" />
            </button>
            <div className="flex-1" />
            <Button size="sm" variant="accent" onClick={() => setAction("assign")}>
              <Send className="h-4 w-4" />
              {t("vehicles.assignTo")}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setAction("edit")}>
              <Pencil className="h-4 w-4" />
              {t("vehicles.bulkEdit")}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setAction("remove")}>
              <Trash2 className="h-4 w-4 text-offline" />
              {t("vehicles.remove")}
            </Button>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-xs font-medium uppercase tracking-wide text-muted">
              <tr>
                {canEdit && (
                  <th className="w-10 px-4 py-3">
                    <Checkbox
                      label={t("vehicles.selectAll")}
                      checked={ids.length > 0 && chosen.length === ids.length}
                      indeterminate={chosen.length > 0}
                      onChange={(on) => setSelected(on ? new Set(ids) : new Set())}
                    />
                  </th>
                )}
                <th className="px-4 py-3">{t("vehicles.plate")}</th>
                <th className="px-4 py-3">{t("vehicles.department")}</th>
                <th className="px-4 py-3">{t("vehicles.location")}</th>
                <th className="px-4 py-3">{t("vehicles.group")}</th>
                {consoles.map((c) => (
                  <th key={c.id} className="whitespace-nowrap px-4 py-3" title={c.location}>
                    {c.name}
                  </th>
                ))}
                {canEdit && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {items.map((v) => (
                <tr key={v.id} className={selected.has(v.id) ? "bg-lucht/10" : "hover:bg-surface/60"}>
                  {canEdit && (
                    <td className="px-4 py-2.5">
                      <Checkbox checked={selected.has(v.id)} onChange={(on) => toggle(v.id, on)} />
                    </td>
                  )}
                  <td className="px-4 py-2.5">
                    <Plate value={v.plate} />
                    {v.description && <div className="mt-1 text-xs text-muted">{v.description}</div>}
                  </td>
                  <td className="px-4 py-2.5 font-medium">{v.department || "–"}</td>
                  <td className="px-4 py-2.5">
                    <Tag>{v.location}</Tag>
                  </td>
                  <td className="px-4 py-2.5 text-muted">{v.group_name || "–"}</td>
                  {consoles.map((c) => (
                    <td key={c.id} className="px-4 py-2.5">
                      {c.last_scan_at || v.presence[String(c.id)] ? <PresenceCell presence={v.presence[String(c.id)]} /> : <span className="text-xs text-muted" title={t("vehicles.notScanned")}>?</span>}
                    </td>
                  ))}
                  {canEdit && (
                    <td className="px-4 py-2.5 text-right">
                      <Button variant="ghost" size="icon" onClick={() => setEditing(v)} aria-label={t("common.edit")}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
              {list.data && !items.length && (
                <tr>
                  <td colSpan={6 + consoles.length} className="px-6 py-14 text-center">
                    <Truck className="mx-auto h-8 w-8 text-muted" />
                    <div className="mt-3 font-semibold">{t("vehicles.emptyTitle")}</div>
                    <div className="mt-1 text-sm text-muted">{t("vehicles.emptyBody")}</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {list.data && (
          <div className="border-t border-line px-4 py-3 text-sm text-muted">{t("vehicles.count", { count: items.length })}</div>
        )}
      </Card>

      {editing !== null && <VehicleDialog vehicle={editing} onClose={() => setEditing(null)} />}
      {(action === "assign" || action === "remove") && (
        <AssignDialog ids={chosen} consoles={consoles} mode={action} onClose={() => setAction(null)} onJob={setJobId} />
      )}
      {action === "edit" && <BulkEditDialog ids={chosen} onClose={() => setAction(null)} />}
      {action === "adopt" && adopt.data && <AdoptDialog candidates={adopt.data} onClose={() => setAction(null)} />}
      <JobDialog jobId={jobId} onClose={() => setJobId(null)} onFinished={refresh} />
    </>
  );
}
