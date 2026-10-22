import type { FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Send } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { useSettingsForm } from "@/lib/useSettingsForm";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Alert, Badge, PageHeader } from "@/components/ui/misc";

interface Notifications extends Record<string, unknown> {
  recipients: string;
  import_report: "failure" | "always" | "never";
  sync_failure: boolean;
  update_available: boolean;
}

export function NotificationsPage() {
  const { t } = useTranslation();
  const { form, set, save, saved } = useSettingsForm<Notifications>("notifications");
  const test = useMutation({ mutationFn: () => api<{ to: string }>("/settings/notifications/test", { method: "POST" }) });
  if (!form) return null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(form);
  };

  return (
    <form onSubmit={submit}>
      <PageHeader
        title={t("notifications.title")}
        description={t("notifications.description")}
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
          {save.isError && <Alert tone="danger">{errorMessage(t, save.error, "notifications")}</Alert>}
          <Card>
            <CardHeader title={t("notifications.recipients")} />
            <CardBody>
              <Field label={t("notifications.recipients")} hint={t("notifications.recipientsHint")}>
                <Input value={form.recipients} onChange={(e) => set("recipients", e.target.value)} placeholder="ict@example.com, planning@example.com" />
              </Field>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={t("notifications.events")} />
            <CardBody className="space-y-5">
              <Field label={t("notifications.importReport")} hint={t("notifications.importReportHint")}>
                <Select value={form.import_report} onChange={(e) => set("import_report", e.target.value)}>
                  <option value="failure">{t("notifications.onProblems")}</option>
                  <option value="always">{t("notifications.always")}</option>
                  <option value="never">{t("notifications.never")}</option>
                </Select>
              </Field>
              <Switch checked={form.sync_failure} onChange={(v) => set("sync_failure", v)} label={t("notifications.syncFailure")} description={t("notifications.syncFailureHint")} />
              <Switch checked={form.update_available} onChange={(v) => set("update_available", v)} label={t("notifications.updateAvailable")} description={t("notifications.updateAvailableHint")} />
            </CardBody>
          </Card>
        </div>
        <div>
          <Card className="lg:sticky lg:top-24">
            <CardHeader title={t("notifications.test")} />
            <CardBody className="space-y-4 text-sm">
              <p className="text-muted">
                {t("notifications.testHint")}{" "}
                <Link to="/admin/mail" className="font-semibold text-accent-text hover:underline">
                  {t("nav.mail")}
                </Link>
              </p>
              <Button type="button" variant="secondary" className="w-full" onClick={() => test.mutate()} loading={test.isPending} disabled={!form.recipients.trim()}>
                <Send className="h-4 w-4" />
                {t("notifications.test")}
              </Button>
              {test.isSuccess && <Alert tone="success">{t("mail.testSent", { to: test.data.to })}</Alert>}
              {test.isError && <Alert tone="danger">{errorMessage(t, test.error, "notifications")}</Alert>}
            </CardBody>
          </Card>
        </div>
      </div>
    </form>
  );
}
