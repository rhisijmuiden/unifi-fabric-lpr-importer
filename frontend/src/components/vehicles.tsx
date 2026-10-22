import { useTranslation } from "react-i18next";
import { Check, Minus } from "lucide-react";
import type { Presence } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { cn } from "@/lib/utils";

export function Plate({ value, className }: { value: string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-md bg-raised px-2 py-0.5 font-mono text-[13px] font-bold tracking-wider text-ink ring-1 ring-line", className)}>
      {value}
    </span>
  );
}

/** Present / not present on one console, with the Access user and groups on hover. */
export function PresenceCell({ presence }: { presence?: Presence }) {
  const { t } = useTranslation();
  if (!presence) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-muted" title={t("vehicles.absent")}>
        <Minus className="h-3.5 w-3.5" />
        {t("vehicles.absent")}
      </span>
    );
  }
  const title = [presence.user, ...presence.groups].filter(Boolean).join("\n");
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-online/10 px-2 py-0.5 text-xs font-semibold text-online" title={title}>
      <Check className="h-3.5 w-3.5" />
      {t("vehicles.present")}
    </span>
  );
}

export function Checkbox({ checked, indeterminate, onChange, label }: { checked: boolean; indeterminate?: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      className="h-4 w-4 cursor-pointer rounded border-line accent-[var(--primary)]"
      checked={checked}
      ref={(el) => {
        if (el) el.indeterminate = !!indeterminate && !checked;
      }}
      onChange={(e) => onChange(e.target.checked)}
    />
  );
}

export function useCanEdit() {
  const { data: me } = useMe();
  return me?.role === "admin" || me?.role === "operator";
}

/** Department and location chips used in lists. */
export function Tag({ children }: { children: string }) {
  if (!children) return <span className="text-muted">–</span>;
  return <span className="inline-flex rounded-full bg-surface px-2 py-0.5 text-xs font-semibold text-ink ring-1 ring-line">{children}</span>;
}
