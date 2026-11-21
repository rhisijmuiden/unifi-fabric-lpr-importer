import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";
import { Check, DatabaseBackup, Loader2, Sparkles } from "lucide-react";
import { api, type SetupStatus, type WebChange } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { channelLabel, cn } from "@/lib/utils";
import { setLanguage } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { WebAccessForm, redirectAfterRestart } from "@/components/WebAccessForm";

const STEPS = ["welcome", "account", "web", "channel", "data", "finish"] as const;
type Step = (typeof STEPS)[number];

function Choice({ active, onClick, title, hint, icon }: { active: boolean; onClick: () => void; title: string; hint: string; icon?: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn("w-full rounded-xl border p-4 text-left transition", active ? "border-lucht bg-lucht/10 ring-1 ring-lucht" : "border-line hover:bg-surface")}
    >
      <div className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
      </div>
      <div className="mt-1 text-xs text-muted">{hint}</div>
    </button>
  );
}

export function SetupPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const status = useQuery({ queryKey: ["setup-status"], queryFn: () => api<SetupStatus>("/setup/status") });
  const [step, setStep] = useState<Step>("welcome");
  const [lang, setLang] = useState<"en" | "nl">(i18n.language === "nl" ? "nl" : "en");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [email, setEmail] = useState(me?.email ?? "");
  const [web, setWeb] = useState<WebChange | null>(null);
  const [channel, setChannel] = useState<string>("main");
  const [restore, setRestore] = useState(false);
  const [done, setDone] = useState<{ base_url: string; restart: boolean; channel_switch: boolean; applied: boolean; message: string } | null>(null);

  useEffect(() => {
    const s = status.data;
    if (s?.web && !web) {
      setWeb({ mode: s.web.mode, host: s.web.host, cert_pem: "", key_pem: "" });
      setChannel(s.channel === "test" ? "test" : "main");
    }
  }, [status.data, web]);

  const account = useMutation({
    mutationFn: () => api("/setup/account", { method: "PUT", body: { new_password: password, email, language: lang } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
      setStep("web");
    },
  });
  const finish = useMutation({
    mutationFn: () =>
      api<{ base_url: string; restart: boolean; channel_switch: boolean; applied: boolean; message: string }>("/setup/complete", {
        method: "POST",
        body: { web, channel },
      }),
    onSuccess: (r) => {
      qc.setQueryData(["setup-status"], { pending: false });
      setDone(r);
      if (!r.applied) return;
      const target = restore ? "/admin/backup" : "/";
      if (r.restart || r.channel_switch) {
        redirectAfterRestart(r.base_url.replace(/\/$/, "") + target, 10);
      } else {
        navigate(target, { replace: true });
      }
    },
  });

  if (status.data && !status.data.pending && !done) return <Navigate to="/" replace />;

  const index = STEPS.indexOf(step);
  const go = (delta: number) => setStep(STEPS[Math.min(STEPS.length - 1, Math.max(0, index + delta))]);
  const pickLanguage = (l: "en" | "nl") => {
    setLang(l);
    setLanguage(l);
  };
  const passwordError = password && password.length < 10 ? t("setup.passwordShort") : password2 && password !== password2 ? t("setup.passwordMismatch") : null;
  const submitAccount = (e: FormEvent) => {
    e.preventDefault();
    if (!passwordError && password === password2) account.mutate();
  };
  const webValid = !!web && !!web.host && (web.mode !== "own" || (!!web.cert_pem && !!web.key_pem));

  return (
    <div className="flex min-h-screen">
      <aside className="relative hidden w-80 shrink-0 overflow-hidden bg-nacht p-10 text-white lg:block">
        <img src="/brand/rhis-antenne.svg" alt="" className="pointer-events-none absolute -right-20 -bottom-20 h-80 w-80 opacity-10" />
        <img src="/brand/rhis-logo-wit.svg" alt="RHIS" className="h-7 w-auto" />
        <div className="mt-12 text-xs font-semibold uppercase tracking-wider text-lucht">{t("setup.title")}</div>
        <ol className="relative mt-6 space-y-1">
          {STEPS.map((s, i) => (
            <li key={s} className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm", s === step ? "bg-white/10 font-semibold" : "text-white/60")}>
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold",
                  i < index ? "bg-lucht text-nacht" : s === step ? "bg-koraal text-nacht" : "bg-white/10",
                )}
              >
                {i < index ? <Check className="h-3.5 w-3.5" /> : i + 1}
              </span>
              {t(`setup.steps.${s}`)}
            </li>
          ))}
        </ol>
      </aside>

      <main className="flex flex-1 items-start justify-center overflow-y-auto p-6 sm:p-10 lg:items-center">
        <div className="w-full max-w-2xl">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted lg:hidden">
            {t("setup.stepOf", { step: index + 1, total: STEPS.length })} · {t(`setup.steps.${step}`)}
          </div>

          {step === "welcome" && (
            <section className="space-y-6">
              <div>
                <h1 className="font-display-wide text-3xl tracking-tight">{t("setup.welcomeTitle")}</h1>
                <p className="mt-2 text-muted">{t("setup.welcomeText")}</p>
              </div>
              <div>
                <div className="mb-2 text-sm font-semibold">{t("setup.language")}</div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Choice active={lang === "en"} onClick={() => pickLanguage("en")} title="English" hint={t("setup.languageHint")} />
                  <Choice active={lang === "nl"} onClick={() => pickLanguage("nl")} title="Nederlands" hint={t("setup.languageHint")} />
                </div>
              </div>
              <div className="flex justify-end">
                <Button variant="accent" onClick={() => go(1)}>
                  {t("setup.start")}
                </Button>
              </div>
            </section>
          )}

          {step === "account" && (
            <form onSubmit={submitAccount} className="space-y-6">
              <div>
                <h1 className="font-display-wide text-2xl tracking-tight">{t("setup.accountTitle")}</h1>
                <p className="mt-2 text-muted">{t("setup.accountText", { username: me?.username ?? "admin" })}</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("setup.newPassword")} hint={t("setup.passwordHint")}>
                  <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus />
                </Field>
                <Field label={t("setup.repeatPassword")}>
                  <Input type="password" autoComplete="new-password" value={password2} onChange={(e) => setPassword2(e.target.value)} required />
                </Field>
                <Field label={t("setup.email")} hint={t("setup.emailHint")} className="sm:col-span-2">
                  <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                </Field>
              </div>
              {passwordError && <Alert tone="warning">{passwordError}</Alert>}
              {account.isError && <Alert tone="danger">{errorMessage(t, account.error, "setup")}</Alert>}
              <div className="flex justify-between">
                <Button type="button" variant="ghost" onClick={() => go(-1)}>
                  {t("common.previous")}
                </Button>
                <Button type="submit" loading={account.isPending} disabled={!password || password !== password2 || !!passwordError}>
                  {t("common.next")}
                </Button>
              </div>
            </form>
          )}

          {step === "web" && web && (
            <section className="space-y-6">
              <div>
                <h1 className="font-display-wide text-2xl tracking-tight">{t("setup.webTitle")}</h1>
                <p className="mt-2 text-muted">{t("setup.webText")}</p>
              </div>
              <WebAccessForm value={web} onChange={setWeb} />
              <div className="flex justify-between">
                <Button variant="ghost" onClick={() => go(-1)}>
                  {t("common.previous")}
                </Button>
                <Button onClick={() => go(1)} disabled={!webValid}>
                  {t("common.next")}
                </Button>
              </div>
            </section>
          )}

          {step === "channel" && (
            <section className="space-y-6">
              <div>
                <h1 className="font-display-wide text-2xl tracking-tight">{t("setup.channelTitle")}</h1>
                <p className="mt-2 text-muted">{t("setup.channelText")}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Choice active={channel === "main"} onClick={() => setChannel("main")} title={t("system.production")} hint={t("system.productionHint")} />
                <Choice active={channel === "test"} onClick={() => setChannel("test")} title={t("system.test")} hint={t("system.testHint")} />
              </div>
              <div className="flex justify-between">
                <Button variant="ghost" onClick={() => go(-1)}>
                  {t("common.previous")}
                </Button>
                <Button onClick={() => go(1)}>{t("common.next")}</Button>
              </div>
            </section>
          )}

          {step === "data" && (
            <section className="space-y-6">
              <div>
                <h1 className="font-display-wide text-2xl tracking-tight">{t("setup.dataTitle")}</h1>
                <p className="mt-2 text-muted">{t("setup.dataText")}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Choice active={!restore} onClick={() => setRestore(false)} icon={<Sparkles className="h-4 w-4" />} title={t("setup.fresh")} hint={t("setup.freshHint")} />
                <Choice active={restore} onClick={() => setRestore(true)} icon={<DatabaseBackup className="h-4 w-4" />} title={t("setup.restore")} hint={t("setup.restoreHint")} />
              </div>
              <div className="flex justify-between">
                <Button variant="ghost" onClick={() => go(-1)}>
                  {t("common.previous")}
                </Button>
                <Button onClick={() => go(1)}>{t("common.next")}</Button>
              </div>
            </section>
          )}

          {step === "finish" && web && (
            <section className="space-y-6">
              <div>
                <h1 className="font-display-wide text-2xl tracking-tight">{t("setup.finishTitle")}</h1>
                <p className="mt-2 text-muted">{t("setup.finishText")}</p>
              </div>
              <dl className="divide-y divide-line rounded-xl border border-line text-sm">
                {[
                  [t("setup.language"), lang === "nl" ? "Nederlands" : "English"],
                  [t("setup.address"), `${web.mode === "http" ? "http" : "https"}://${web.host}:8080`],
                  [t("web.mode"), t(`web.modes.${web.mode === "keep" ? "http" : web.mode}`)],
                  [t("system.channel"), channelLabel(channel, t)],
                  [t("setup.steps.data"), restore ? t("setup.restore") : t("setup.fresh")],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4 px-4 py-3">
                    <dt className="text-muted">{k}</dt>
                    <dd className="text-right font-semibold">{v}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-xs text-muted">{t("setup.later")}</p>
              {finish.isError && <Alert tone="danger">{errorMessage(t, finish.error, "web")}</Alert>}
              {done && !done.applied && (
                <>
                  <Alert tone="warning">{t("setup.notApplied", { message: done.message })}</Alert>
                  <div className="flex justify-end">
                    <Button onClick={() => navigate(restore ? "/admin/backup" : "/", { replace: true })}>{t("setup.continue")}</Button>
                  </div>
                </>
              )}
              {done && done.applied && (done.restart || done.channel_switch) ? (
                <Alert tone="info">
                  <div className="flex items-center gap-2 font-medium">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {done.channel_switch ? t("setup.switching") : t("web.restarting")}
                  </div>
                  <div className="mt-1">
                    {t("web.openingAt")}{" "}
                    <a className="font-mono underline" href={done.base_url}>
                      {done.base_url}
                    </a>
                  </div>
                </Alert>
              ) : done ? null : (
                <div className="flex justify-between">
                  <Button variant="ghost" onClick={() => go(-1)} disabled={finish.isPending}>
                    {t("common.previous")}
                  </Button>
                  <Button variant="accent" loading={finish.isPending} onClick={() => finish.mutate()}>
                    {t("setup.finish")}
                  </Button>
                </div>
              )}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
