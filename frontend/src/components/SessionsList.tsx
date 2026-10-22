import { useTranslation } from "react-i18next";
import { LogOut, Monitor } from "lucide-react";
import type { SessionInfo } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/misc";

/** A short readable name for a browser user agent, e.g. "Edge on Windows". */
export function describeAgent(ua: string) {
  if (!ua) return "–";
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : ua.split(" ")[0];
  const os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS X/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${browser} · ${os}` : browser;
}

export function SessionsList({ sessions, onEnd, showUser, ending }: { sessions: SessionInfo[]; onEnd: (s: SessionInfo) => void; showUser?: boolean; ending?: string | null }) {
  const { t, i18n } = useTranslation();
  if (!sessions.length) return <p className="py-6 text-center text-sm text-muted">{t("security.noSessions")}</p>;
  return (
    <ul className="divide-y divide-line">
      {sessions.map((s) => (
        <li key={s.id} className="flex items-center gap-3 py-3 text-sm">
          <Monitor className="h-5 w-5 shrink-0 text-muted" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 font-semibold">
              {showUser && <span>{s.username}</span>}
              <span className={showUser ? "font-normal text-muted" : ""} title={s.user_agent}>
                {describeAgent(s.user_agent)}
              </span>
              {s.current && <Badge tone="brand">{t("security.thisSession")}</Badge>}
            </div>
            <div className="text-xs text-muted">
              {s.ip_address || "–"} · {t("security.lastActive", { date: formatDate(s.last_seen_at, i18n.language) })} · {t("security.signedIn", { date: formatDate(s.created_at, i18n.language) })}
            </div>
          </div>
          {!s.current && (
            <Button variant="ghost" size="sm" loading={ending === s.id} onClick={() => onEnd(s)}>
              <LogOut className="h-4 w-4" />
              {t("security.end")}
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}
