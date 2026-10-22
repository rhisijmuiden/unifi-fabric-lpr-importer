import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Copy, ExternalLink, Network, Plus, Trash2 } from "lucide-react";
import { api, type ApiKey } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Switch } from "@/components/ui/form";
import { Alert, Badge, Dialog, PageHeader } from "@/components/ui/misc";

const parseNetworks = (value: string) =>
  value
    .split(/[\s,;]+/)
    .map((v) => v.trim())
    .filter(Boolean);

function NetworksDialog({ apiKey, onClose }: { apiKey: ApiKey; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [value, setValue] = useState(apiKey.allowed_ips.join(", "));
  const save = useMutation({
    mutationFn: () => api(`/api-keys/${apiKey.id}`, { method: "PATCH", body: { allowed_ips: parseNetworks(value) } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["api-keys"] });
      onClose();
    },
  });
  return (
    <Dialog open onClose={onClose} title={t("apiKeys.networksFor", { name: apiKey.name })}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
        className="space-y-4"
      >
        {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "apiKeys")}</Alert>}
        <Field label={t("apiKeys.networks")} hint={t("apiKeys.networksHint")}>
          <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="203.0.113.10, 10.20.0.0/16" className="font-mono" />
        </Field>
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

function NewKeyDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [name, setName] = useState("Lobster");
  const [allowDelete, setAllowDelete] = useState(false);
  const [networks, setNetworks] = useState("");
  const [copied, setCopied] = useState(false);
  const create = useMutation({
    mutationFn: () => api<ApiKey & { key: string }>("/api-keys", { method: "POST", body: { name, allow_delete: allowDelete, allowed_ips: parseNetworks(networks) } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  if (create.data) {
    return (
      <Dialog open onClose={onClose} title={t("apiKeys.created")}>
        <div className="space-y-4">
          <Alert tone="warning">{t("apiKeys.copyOnce")}</Alert>
          <div className="flex gap-2">
            <Input readOnly value={create.data.key} className="font-mono text-xs" onFocus={(e) => e.target.select()} />
            <Button
              variant="outline"
              onClick={() => {
                navigator.clipboard?.writeText(create.data!.key).then(() => setCopied(true));
              }}
            >
              <Copy className="h-4 w-4" />
              {copied ? t("apiKeys.copied") : t("apiKeys.copy")}
            </Button>
          </div>
          <div className="flex justify-end">
            <Button onClick={onClose}>{t("common.close")}</Button>
          </div>
        </div>
      </Dialog>
    );
  }
  return (
    <Dialog open onClose={onClose} title={t("apiKeys.add")}>
      <form onSubmit={submit} className="space-y-4">
        {create.isError && <Alert tone="danger">{errorMessage(t, create.error, "apiKeys")}</Alert>}
        <Field label={t("apiKeys.name")} hint={t("apiKeys.nameHint")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label={t("apiKeys.networks")} hint={t("apiKeys.networksHint")}>
          <Input value={networks} onChange={(e) => setNetworks(e.target.value)} placeholder="203.0.113.10, 10.20.0.0/16" className="font-mono" />
        </Field>
        <Switch checked={allowDelete} onChange={setAllowDelete} label={t("apiKeys.allowDelete")} description={t("apiKeys.allowDeleteHint")} />
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" loading={create.isPending}>
            {t("apiKeys.create")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function ApiKeysPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<ApiKey | null>(null);
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: () => api<ApiKey[]>("/api-keys") });
  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: number; is_active?: boolean; allow_delete?: boolean }) => api(`/api-keys/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });
  const remove = useMutation({
    mutationFn: (k: ApiKey) => api(`/api-keys/${k.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });

  return (
    <>
      <PageHeader
        title={t("apiKeys.title")}
        description={t("apiKeys.description")}
        action={
          <Button onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" />
            {t("apiKeys.add")}
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-2">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface text-left text-xs font-medium uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-5 py-3">{t("apiKeys.name")}</th>
                  <th className="px-5 py-3">{t("apiKeys.rights")}</th>
                  <th className="px-5 py-3">{t("apiKeys.networks")}</th>
                  <th className="px-5 py-3">{t("apiKeys.lastUsed")}</th>
                  <th className="px-5 py-3">{t("users.status")}</th>
                  <th className="px-5 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {keys.data?.map((k) => (
                  <tr key={k.id}>
                    <td className="px-5 py-3">
                      <div className="font-semibold">{k.name}</div>
                      <div className="font-mono text-xs text-muted">{k.prefix}…</div>
                    </td>
                    <td className="px-5 py-3">
                      <button onClick={() => update.mutate({ id: k.id, allow_delete: !k.allow_delete })} title={t("apiKeys.toggleDelete")}>
                        <Badge tone={k.allow_delete ? "warning" : "neutral"}>{k.allow_delete ? t("apiKeys.readWriteDelete") : t("apiKeys.readWrite")}</Badge>
                      </button>
                    </td>
                    <td className="px-5 py-3">
                      <button onClick={() => setEditing(k)} title={t("apiKeys.toggleDelete")} className="inline-flex items-center gap-1.5 text-left">
                        <Network className="h-3.5 w-3.5 shrink-0 text-muted" />
                        {k.allowed_ips.length ? <span className="font-mono text-xs">{k.allowed_ips.join(", ")}</span> : <span className="text-muted">{t("apiKeys.anyAddress")}</span>}
                      </button>
                    </td>
                    <td className="px-5 py-3 text-muted">{k.last_used_at ? formatDate(k.last_used_at, i18n.language) : t("common.never")}</td>
                    <td className="px-5 py-3">
                      <button onClick={() => update.mutate({ id: k.id, is_active: !k.is_active })}>
                        <Badge tone={k.is_active ? "success" : "neutral"}>{k.is_active ? t("common.active") : t("common.inactive")}</Badge>
                      </button>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Button variant="ghost" size="icon" aria-label={t("common.delete")} onClick={() => window.confirm(t("common.confirmDelete", { name: k.name })) && remove.mutate(k)}>
                        <Trash2 className="h-4 w-4 text-offline" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {keys.data && !keys.data.length && (
                  <tr>
                    <td colSpan={6} className="px-6 py-10 text-center text-muted">
                      {t("apiKeys.empty")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <CardHeader title={t("apiKeys.docsTitle")} />
          <CardBody className="space-y-3 text-sm">
            <p className="text-muted">{t("apiKeys.docsBody")}</p>
            <pre className="overflow-x-auto rounded-md bg-nacht p-3 font-mono text-xs text-white">{`curl -X POST ${location.origin}/api/v1/vehicles \\
  -H "Authorization: Bearer lpr_…" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -H "Content-Type: application/json" \\
  -d '{"vehicles":[{"plate":"12-BDF-3",
       "department":"Netwerktransport",
       "location":"Wognum"}]}'`}</pre>
            <a href="/api/docs" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-accent-text hover:underline">
              {t("apiKeys.openDocs")}
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
            <p className="text-xs text-muted">{t("apiKeys.guide")}</p>
          </CardBody>
        </Card>
      </div>
      {adding && <NewKeyDialog onClose={() => setAdding(false)} />}
      {editing && <NetworksDialog apiKey={editing} onClose={() => setEditing(null)} />}
    </>
  );
}
