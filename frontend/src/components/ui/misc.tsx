import { useEffect, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "success" | "warning" | "danger" | "brand";

// Status colours are only for status, always paired with text (RHIS huisstijl).
const badgeTones: Record<Tone, string> = {
  neutral: "bg-surface text-muted ring-1 ring-line",
  success: "bg-online/10 text-online",
  warning: "bg-warning/10 text-warning",
  danger: "bg-offline/10 text-offline",
  brand: "bg-lucht/25 text-nacht dark:bg-lucht/15 dark:text-lucht",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold", badgeTones[tone], className)}>
      {children}
    </span>
  );
}

const alertIcons = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: XCircle };
const alertTones = {
  info: "border-lucht/60 bg-lucht/15 text-ink",
  success: "border-online/30 bg-online/10 text-ink",
  warning: "border-warning/30 bg-warning/10 text-ink",
  danger: "border-offline/30 bg-offline/10 text-ink",
};
const alertIconTones = { info: "text-nacht dark:text-lucht", success: "text-online", warning: "text-warning", danger: "text-offline" };

export function Alert({ tone = "info", children }: { tone?: keyof typeof alertIcons; children: ReactNode }) {
  const Icon = alertIcons[tone];
  return (
    <div className={cn("flex gap-3 rounded-md border px-4 py-3 text-sm", alertTones[tone])}>
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", alertIconTones[tone])} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export function Dialog({ open, onClose, title, children, wide, xl }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean; xl?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-nacht/60 p-4 backdrop-blur-sm sm:items-center" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className={cn("w-full rounded-lg border border-line bg-raised shadow-2xl", xl ? "max-w-4xl" : wide ? "max-w-2xl" : "max-w-lg")}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="text-base font-bold">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-surface hover:text-ink" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

export function PageHeader({ title, description, action }: { title: ReactNode; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display-wide text-2xl tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}
