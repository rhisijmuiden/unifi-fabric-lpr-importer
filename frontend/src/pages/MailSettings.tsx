import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { useSettingsForm } from "@/lib/useSettingsForm";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Alert, Badge, PageHeader } from "@/components/ui/misc";

interface Smtp extends Record<string, unknown> {
  host: string;
  port: number;
  security: "none" | "starttls" | "ssl";
  auth_method: "none" | "password" | "oauth2_m365";
  username: string;
  password_set: boolean;
  oauth_tenant_id: string;
  oauth_client_id: string;
  oauth_client_secret_set: boolean;
  from_address: string;
  from_name: string;
  verify_tls: boolean;
}

export function MailSettingsPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const { form, set, save, saved } = useSettingsForm<Smtp>("smtp");
  const [password, setPassword] = useState("");
  const [oauthSecret, setOauthSecret] = useState("");
  const [testTo, setTestTo] = useState(me?.email ?? "");
  const test = useMutation({ mutationFn: () => api("/settings/smtp/test", { method: "POST", body: { to: testTo } }) });
  if (!form) return null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const { password_set: _p, oauth_client_secret_set: _o, ...rest } = form;
    save.mutate(
      { ...rest, password: password || null, oauth_client_secret: oauthSecret || null },
      {
        onSuccess: () => {
          setPassword("");
          setOauthSecret("");
        },
      },
    );
  };

  const changeSecurity = (value: Smtp["security"]) => {
    set("security", value);
    if (value === "ssl" && form.port === 587) set("port", 465);
    if (value === "starttls" && form.port === 465) set("port", 587);
  };

  return (
    <form onSubmit={submit}>
      <PageHeader
        title={t("mail.title")}
        description={t("mail.description")}
        action={
          <div className="flex items-center gap-3">
            {saved && <Badge tone="success">{t("common.saved")}</Badge>}
            <Button type="submit" loading={save.isPending}>
              {t("common.save")}
            </Button>
          </div>
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {save.isError && <Alert tone="danger">{errorMessage(t, save.error)}</Alert>}
          <Card>
            <CardHeader title={t("mail.server")} />
            <CardBody className="grid gap-4 sm:grid-cols-3">
              <Field label={t("mail.host")} className="sm:col-span-2">
                <Input value={form.host} onChange={(e) => set("host", e.target.value.trim())} placeholder="smtp.office365.com" />
              </Field>
              <Field label={t("mail.port")}>
                <Input type="number" min={1} max={65535} value={form.port} onChange={(e) => set("port", Number(e.target.value))} />
              </Field>
              <Field label={t("mail.security")} className="sm:col-span-3">
                <Select value={form.security} onChange={(e) => changeSecurity(e.target.value as Smtp["security"])}>
                  <option value="starttls">{t("mail.securityStarttls")}</option>
                  <option value="ssl">{t("mail.securitySsl")}</option>
                  <option value="none">{t("mail.securityNone")}</option>
                </Select>
              </Field>
              <div className="sm:col-span-3">
                <Switch checked={form.verify_tls} onChange={(v) => set("verify_tls", v)} label={t("mail.verifyTls")} />
              </div>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={t("mail.authentication")} />
            <CardBody className="grid gap-4 sm:grid-cols-2">
              <Field label={t("mail.authMethod")} className="sm:col-span-2">
                <Select value={form.auth_method} onChange={(e) => set("auth_method", e.target.value)}>
                  <option value="password">{t("mail.authPassword")}</option>
                  <option value="oauth2_m365">{t("mail.authOauth")}</option>
                  <option value="none">{t("mail.authNone")}</option>
                </Select>
              </Field>
              {form.auth_method !== "none" && (
                <Field label={t("mail.username")} className="sm:col-span-2">
                  <Input value={form.username} onChange={(e) => set("username", e.target.value.trim())} autoComplete="off" />
                </Field>
              )}
              {form.auth_method === "password" && (
                <Field label={t("mail.password")} hint={form.password_set ? t("common.unchanged") : undefined} className="sm:col-span-2">
                  <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={form.password_set ? "••••••••" : ""} />
                </Field>
              )}
              {form.auth_method === "oauth2_m365" && (
                <>
                  <div className="sm:col-span-2">
                    <Alert>{t("mail.oauthHint")}</Alert>
                  </div>
                  <Field label={t("mail.oauthTenant")}>
                    <Input value={form.oauth_tenant_id} onChange={(e) => set("oauth_tenant_id", e.target.value.trim())} />
                  </Field>
                  <Field label={t("mail.oauthClient")}>
                    <Input value={form.oauth_client_id} onChange={(e) => set("oauth_client_id", e.target.value.trim())} />
                  </Field>
                  <Field label={t("mail.oauthSecret")} hint={form.oauth_client_secret_set ? t("common.unchanged") : undefined} className="sm:col-span-2">
                    <Input type="password" autoComplete="off" value={oauthSecret} onChange={(e) => setOauthSecret(e.target.value)} placeholder={form.oauth_client_secret_set ? "••••••••" : ""} />
                  </Field>
                </>
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={t("mail.sender")} />
            <CardBody className="grid gap-4 sm:grid-cols-2">
              <Field label={t("mail.fromAddress")}>
                <Input type="email" value={form.from_address} onChange={(e) => set("from_address", e.target.value.trim())} placeholder="noreply@example.com" />
              </Field>
              <Field label={t("mail.fromName")}>
                <Input value={form.from_name} onChange={(e) => set("from_name", e.target.value)} />
              </Field>
            </CardBody>
          </Card>
        </div>
        <div>
          <Card className="lg:sticky lg:top-24">
            <CardHeader title={t("mail.test")} />
            <CardBody className="space-y-4">
              <Field label={t("mail.testTo")}>
                <Input type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} />
              </Field>
              <Button type="button" variant="secondary" className="w-full" onClick={() => test.mutate()} loading={test.isPending} disabled={!testTo}>
                <Send className="h-4 w-4" />
                {t("mail.test")}
              </Button>
              {test.isSuccess && <Alert tone="success">{t("mail.testSent", { to: testTo })}</Alert>}
              {test.isError && <Alert tone="danger">{errorMessage(t, test.error)}</Alert>}
            </CardBody>
          </Card>
        </div>
      </div>
    </form>
  );
}
