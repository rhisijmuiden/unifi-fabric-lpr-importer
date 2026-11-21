import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { api, type WebChange, type WebInfo } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert, Badge } from "@/components/ui/misc";
import { WebAccessForm, redirectAfterRestart } from "@/components/WebAccessForm";

export function WebAccessCard() {
  const { t, i18n } = useTranslation();
  const info = useQuery({ queryKey: ["web-info"], queryFn: () => api<WebInfo>("/system/web") });
  const [form, setForm] = useState<WebChange | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  useEffect(() => {
    if (info.data && !form) setForm({ mode: info.data.mode, host: info.data.host, cert_pem: "", key_pem: "" });
  }, [info.data, form]);
  const apply = useMutation({
    mutationFn: (body: WebChange) => api<{ base_url: string }>("/system/web", { method: "PUT", body }),
    onSuccess: (r) => {
      setTarget(r.base_url);
      redirectAfterRestart(r.base_url, 10);
    },
  });
  const d = info.data;
  const cert = d?.certificate;
  return (
    <Card className="lg:col-span-3">
      <CardHeader
        title={t("web.title")}
        description={t("web.description")}
        action={d && <Badge tone={d.https ? "success" : "warning"}>{d.https ? "HTTPS" : "HTTP"}</Badge>}
      />
      <CardBody className="space-y-5">
        {d && (
          <div className="text-sm">
            <span className="text-muted">{t("web.current")} </span>
            <span className="font-mono">{d.base_url}</span>
            {cert && (
              <div className="mt-1 text-xs text-muted">
                {cert.self_signed ? t("web.selfSignedCert") : cert.issuer} · {t("web.validUntil", { date: formatDate(cert.not_after, i18n.language) })}
              </div>
            )}
          </div>
        )}
        {form && <WebAccessForm value={form} onChange={setForm} />}
        {apply.isError && <Alert tone="danger">{errorMessage(t, apply.error, "web")}</Alert>}
        {target ? (
          <Alert tone="info">
            <div className="flex items-center gap-2 font-medium">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("web.restarting")}
            </div>
            <div className="mt-1">
              {t("web.openingAt")}{" "}
              <a className="font-mono underline" href={target}>
                {target}
              </a>
            </div>
          </Alert>
        ) : (
          <div className="flex justify-end">
            <Button
              loading={apply.isPending}
              disabled={!form || !form.host || (form.mode === "own" && (!form.cert_pem || !form.key_pem))}
              onClick={() => form && window.confirm(t("web.confirm")) && apply.mutate(form)}
            >
              {t("web.apply")}
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
