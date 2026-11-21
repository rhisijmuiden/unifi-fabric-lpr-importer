import { useTranslation } from "react-i18next";
import { Globe, Lock, ShieldCheck, Upload } from "lucide-react";
import type { WebChange, WebMode } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Field, Input } from "@/components/ui/form";

const MODES: { mode: Exclude<WebMode, "keep">; icon: typeof Globe }[] = [
  { mode: "http", icon: Globe },
  { mode: "selfsigned", icon: Lock },
  { mode: "own", icon: ShieldCheck },
];

function PemInput({ label, hint, value, onChange }: { label: string; hint: string; value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation();
  return (
    <Field label={label} hint={hint}>
      <div className="space-y-2">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          spellCheck={false}
          placeholder="-----BEGIN …-----"
          className="w-full rounded-md border border-line bg-raised px-3 py-2 font-mono text-xs text-ink focus:border-lucht focus:outline-none focus:ring-2 focus:ring-lucht/40 dark:bg-surface"
        />
        <span className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-line bg-raised px-3 py-1.5 text-xs font-semibold hover:bg-surface">
          <Upload className="h-3.5 w-3.5" />
          {t("web.chooseFile")}
          <input
            type="file"
            accept=".pem,.crt,.cer,.key,text/plain"
            className="sr-only"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (file) onChange(await file.text());
            }}
          />
        </span>
      </div>
    </Field>
  );
}

/** Web address and HTTP/HTTPS choice, used in the setup wizard and on System & updates. */
export function WebAccessForm({ value, onChange }: { value: WebChange; onChange: (v: WebChange) => void }) {
  const { t } = useTranslation();
  const set = (patch: Partial<WebChange>) => onChange({ ...value, ...patch });
  const scheme = value.mode === "http" ? "http" : "https";
  return (
    <div className="space-y-5">
      <Field label={t("web.host")} hint={t("web.hostHint")}>
        <Input value={value.host} onChange={(e) => set({ host: e.target.value.trim() })} placeholder="lpr.example.com" autoComplete="off" />
      </Field>
      <div>
        <div className="mb-2 text-sm font-semibold">{t("web.mode")}</div>
        <div className="grid gap-3 sm:grid-cols-3">
          {MODES.map(({ mode, icon: Icon }) => (
            <button
              key={mode}
              type="button"
              onClick={() => set({ mode })}
              className={cn(
                "flex flex-col items-start rounded-xl border p-4 text-left transition",
                value.mode === mode ? "border-lucht bg-lucht/10 ring-1 ring-lucht" : "border-line hover:bg-surface",
              )}
            >
              <Icon className="h-5 w-5 text-nacht dark:text-lucht" />
              <div className="mt-2 text-sm font-semibold">{t(`web.modes.${mode}`)}</div>
              <div className="mt-1 text-xs text-muted">{t(`web.modes.${mode}Hint`)}</div>
            </button>
          ))}
        </div>
      </div>
      {value.mode === "own" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <PemInput label={t("web.certificate")} hint={t("web.certificateHint")} value={value.cert_pem} onChange={(cert_pem) => set({ cert_pem })} />
          <PemInput label={t("web.key")} hint={t("web.keyHint")} value={value.key_pem} onChange={(key_pem) => set({ key_pem })} />
        </div>
      )}
      <div className="rounded-lg border border-dashed border-line px-4 py-3 text-sm">
        <span className="text-muted">{t("web.preview")} </span>
        <span className="font-mono font-semibold">
          {scheme}://{value.host || "…"}:8080
        </span>
      </div>
    </div>
  );
}

/** Wait a few seconds for the restart, then open the application on its (new) address. */
export function redirectAfterRestart(url: string, seconds = 8) {
  window.setTimeout(() => {
    window.location.href = url.replace(/\/$/, "") + "/";
  }, seconds * 1000);
}
