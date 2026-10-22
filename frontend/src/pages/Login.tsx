import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, useSearchParams } from "react-router-dom";
import { api, type User } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { setLanguage } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";

function MicrosoftLogo() {
  return (
    <svg viewBox="0 0 21 21" className="h-4 w-4" aria-hidden="true">
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}

export function LoginPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [params] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(params.get("error") ? t(`login.errors.${params.get("error")}`) : null);
  const [busy, setBusy] = useState(false);
  const config = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => api<{ sso_enabled: boolean; local_login: boolean }>("/auth/config"),
  });

  if (me) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await api<User>("/auth/login", { method: "POST", body: { username, password } });
      setLanguage(user.language);
      qc.setQueryData(["me"], user);
    } catch (err) {
      setError(errorMessage(t, err, "login"));
    } finally {
      setBusy(false);
    }
  };

  const sso = config.data?.sso_enabled;
  const local = config.data?.local_login ?? true;

  return (
    <div className="flex min-h-screen">
      <div className="relative hidden flex-1 overflow-hidden bg-nacht lg:block">
        <img src="/brand/rhis-antenne.svg" alt="" className="pointer-events-none absolute -right-24 -bottom-24 h-[28rem] w-[28rem] opacity-10" />
        <div className="relative flex h-full flex-col justify-between p-12 text-white">
          <img src="/brand/rhis-logo-wit.svg" alt="RHIS" className="h-8 w-auto self-start" />
          <div>
            <span className="mb-6 inline-flex rounded-full bg-lucht/15 px-3 py-1 text-xs font-semibold text-lucht">UniFi Access · UniFi Fabric</span>
            <h2 className="font-display-wide text-4xl leading-tight">{t("app.name")}</h2>
            <p className="mt-4 max-w-md text-lg text-white/70">{t("login.subtitle")}</p>
            <div className="mt-10 inline-flex items-center rounded-md border-2 border-white/80 px-5 py-2 font-mono text-3xl font-bold tracking-widest">
              AB-123-C
            </div>
          </div>
          <div className="text-sm text-white/50">RHIS</div>
        </div>
      </div>
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <img src="/brand/rhis-logo.svg" alt="RHIS" className="h-7 w-auto dark:hidden" />
            <img src="/brand/rhis-logo-wit.svg" alt="RHIS" className="hidden h-7 w-auto dark:block" />
          </div>
          <h1 className="font-display-wide text-2xl tracking-tight">{t("login.title")}</h1>
          <p className="mt-1 text-sm text-muted">{t("login.subtitle")}</p>
          <div className="mt-8 space-y-5">
            {error && <Alert tone="danger">{error}</Alert>}
            {sso && (
              <a
                href="/api/auth/sso/login"
                className="flex h-10 w-full items-center justify-center gap-3 rounded-lg border border-line bg-raised text-sm font-semibold hover:bg-surface"
              >
                <MicrosoftLogo />
                {t("login.sso")}
              </a>
            )}
            {sso && local && (
              <div className="flex items-center gap-3 text-xs uppercase text-muted">
                <div className="h-px flex-1 bg-line" />
                {t("login.or")}
                <div className="h-px flex-1 bg-line" />
              </div>
            )}
            {(local || !sso) && (
              <form onSubmit={submit} className="space-y-4">
                <Field label={t("login.username")}>
                  <Input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
                </Field>
                <Field label={t("login.password")}>
                  <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                </Field>
                <Button type="submit" variant="accent" className="w-full" loading={busy}>
                  {t("login.submit")}
                </Button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
