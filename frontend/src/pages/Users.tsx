import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api, type Role, type User } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Alert, Badge, Dialog, PageHeader } from "@/components/ui/misc";

const ROLES: Role[] = ["admin", "operator", "viewer"];

function UserDialog({ user, onClose }: { user: User | "new" | null; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isNew = user === "new";
  const existing = user && user !== "new" ? user : null;
  const [form, setForm] = useState({
    username: existing?.username ?? "",
    display_name: existing?.display_name ?? "",
    email: existing?.email ?? "",
    role: existing?.role ?? ("viewer" as Role),
    language: existing?.language ?? "en",
    is_active: existing?.is_active ?? true,
    password: "",
  });
  const save = useMutation({
    mutationFn: () => {
      if (isNew) return api("/users", { method: "POST", body: form });
      const { username: _u, password, ...rest } = form;
      return api(`/users/${existing!.id}`, { method: "PATCH", body: password ? { ...rest, password } : rest });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <Dialog open={user !== null} onClose={onClose} title={isNew ? t("users.add") : existing?.username}>
      <form onSubmit={submit} className="space-y-4">
        {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "users")}</Alert>}
        {isNew && (
          <Field label={t("users.username")}>
            <Input value={form.username} onChange={(e) => set("username", e.target.value)} required />
          </Field>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("users.displayName")}>
            <Input value={form.display_name} onChange={(e) => set("display_name", e.target.value)} />
          </Field>
          <Field label={t("users.email")}>
            <Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label={t("users.role")}>
            <Select value={form.role} onChange={(e) => set("role", e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`roles.${r}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("userMenu.language")}>
            <Select value={form.language} onChange={(e) => set("language", e.target.value as "en" | "nl")}>
              <option value="en">English</option>
              <option value="nl">Nederlands</option>
            </Select>
          </Field>
        </div>
        {(isNew || existing?.auth_source === "local") && (
          <Field label={isNew ? t("users.password") : t("users.newPassword")} hint={isNew ? t("users.passwordHint") : t("common.unchanged")}>
            <Input type="password" autoComplete="new-password" minLength={10} required={isNew} value={form.password} onChange={(e) => set("password", e.target.value)} />
          </Field>
        )}
        {!isNew && <Switch checked={form.is_active} onChange={(v) => set("is_active", v)} label={t("common.active")} />}
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

export function UsersPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users") });
  const remove = useMutation({
    mutationFn: (u: User) => api(`/users/${u.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <>
      <PageHeader
        title={t("users.title")}
        description={t("users.description")}
        action={
          <Button onClick={() => setEditing("new")}>
            <Plus className="h-4 w-4" />
            {t("users.add")}
          </Button>
        }
      />
      {remove.isError && (
        <div className="mb-4">
          <Alert tone="danger">{errorMessage(t, remove.error, "users")}</Alert>
        </div>
      )}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-xs font-medium uppercase tracking-wide text-muted">
              <tr>
                <th className="px-6 py-3">{t("users.username")}</th>
                <th className="px-6 py-3">{t("users.role")}</th>
                <th className="px-6 py-3">{t("users.source")}</th>
                <th className="px-6 py-3">{t("users.lastLogin")}</th>
                <th className="px-6 py-3">{t("users.status")}</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.data?.map((u) => (
                <tr key={u.id} className="hover:bg-surface/60">
                  <td className="px-6 py-3">
                    <div className="font-medium">{u.display_name || u.username}</div>
                    <div className="text-xs text-muted">{u.display_name ? u.username : u.email}</div>
                  </td>
                  <td className="px-6 py-3">
                    <Badge tone={u.role === "admin" ? "brand" : "neutral"}>{t(`roles.${u.role}`)}</Badge>
                  </td>
                  <td className="px-6 py-3 text-muted">{t(`users.${u.auth_source}`)}</td>
                  <td className="px-6 py-3 text-muted">{u.last_login_at ? formatDate(u.last_login_at, i18n.language) : t("common.never")}</td>
                  <td className="px-6 py-3">
                    <Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? t("common.active") : t("common.inactive")}</Badge>
                  </td>
                  <td className="px-6 py-3 text-right whitespace-nowrap">
                    <Button variant="ghost" size="icon" onClick={() => setEditing(u)} aria-label={t("common.edit")}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    {u.id !== me?.id && (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("common.delete")}
                        onClick={() => window.confirm(t("common.confirmDelete", { name: u.username })) && remove.mutate(u)}
                      >
                        <Trash2 className="h-4 w-4 text-offline" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {editing !== null && <UserDialog user={editing} onClose={() => setEditing(null)} />}
    </>
  );
}
