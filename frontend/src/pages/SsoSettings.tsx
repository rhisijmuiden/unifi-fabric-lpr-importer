import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Copy } from "lucide-react";
import { errorMessage } from "@/lib/errors";
import { useSettingsForm } from "@/lib/useSettingsForm";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Switch } from "@/components/ui/form";
import { Alert, Badge, PageHeader } from "@/components/ui/misc";

interface Sso extends Record<string, unknown> {
  enabled: boolean;
  tenant_id: string;
  client_id: string;
  client_secret_set: boolean;
  admin_group_id: string;
  operator_group_id: string;
  viewer_group_id: string;
  allow_local_login: boolean;
  redirect_uri: string;
}

export function SsoSettingsPage() {
  const { t } = useTranslation();
  const { form, set, save, saved } = useSettingsForm<Sso>("sso");
  const [secret, setSecret] = useState("");
  if (!form) return null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const { client_secret_set: _s, redirect_uri: _r, ...rest } = form;
    save.mutate({ ...rest, client_secret: secret || null }, { onSuccess: () => setSecret("") });
  };

  return (
    <form onSubmit={submit}>
      <PageHeader
        title={t("sso.title")}
        description={t("sso.description")}
        action={
          <div className="flex items-center gap-3">
            {saved && <Badge tone="success">{t("common.saved")}</Badge>}
            <Button type="submit" loading={save.isPending}>
              {t("common.save")}
            </Button>
          </div>
        }
      />
      <div className="space-y-6">
        {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "sso")}</Alert>}
        <Card>
          <CardBody className="space-y-5">
            <Switch checked={form.enabled} onChange={(v) => set("enabled", v)} label={t("sso.enabled")} description={t("sso.enabledHint")} />
            <Switch checked={form.allow_local_login} onChange={(v) => set("allow_local_login", v)} label={t("sso.allowLocal")} description={t("sso.allowLocalHint")} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Microsoft Entra ID" description={t("sso.howTo")} />
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Field label={t("sso.tenantId")}>
              <Input value={form.tenant_id} onChange={(e) => set("tenant_id", e.target.value.trim())} placeholder="00000000-0000-0000-0000-000000000000" />
            </Field>
            <Field label={t("sso.clientId")}>
              <Input value={form.client_id} onChange={(e) => set("client_id", e.target.value.trim())} placeholder="00000000-0000-0000-0000-000000000000" />
            </Field>
            <Field label={t("sso.clientSecret")} hint={form.client_secret_set ? t("common.unchanged") : undefined}>
              <Input type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={form.client_secret_set ? "••••••••" : ""} />
            </Field>
            <Field label={t("sso.redirectUri")} hint={t("sso.redirectHint")}>
              <div className="flex gap-2">
                <Input readOnly value={form.redirect_uri} className="font-mono text-xs" />
                <Button type="button" variant="outline" size="icon" onClick={() => navigator.clipboard?.writeText(form.redirect_uri)} aria-label="Copy">
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </Field>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("sso.groups")} description={t("sso.groupsHint")} />
          <CardBody className="grid gap-4 sm:grid-cols-3">
            <Field label={t("sso.adminGroup")}>
              <Input value={form.admin_group_id} onChange={(e) => set("admin_group_id", e.target.value.trim())} />
            </Field>
            <Field label={t("sso.operatorGroup")}>
              <Input value={form.operator_group_id} onChange={(e) => set("operator_group_id", e.target.value.trim())} />
            </Field>
            <Field label={t("sso.viewerGroup")}>
              <Input value={form.viewer_group_id} onChange={(e) => set("viewer_group_id", e.target.value.trim())} />
            </Field>
          </CardBody>
        </Card>
      </div>
    </form>
  );
}
