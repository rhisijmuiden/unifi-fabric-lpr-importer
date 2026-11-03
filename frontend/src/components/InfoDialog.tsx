import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useSystemInfo } from "@/lib/system";
import { useMe } from "@/lib/auth";
import { channelLabel, formatDate } from "@/lib/utils";
import { Dialog } from "@/components/ui/misc";
import { UpdatePanel } from "@/components/UpdatePanel";

export function InfoDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const { data: me } = useMe();
  const { data: info } = useSystemInfo();
  return (
    <Dialog open={open} onClose={onClose} title={t("info.title")} wide>
      <div className="flex items-center gap-4">
        <img src="/favicon.svg" alt="" className="h-12 w-12" />
        <div>
          <div className="text-lg font-semibold">UniFi Fabric License Plate Importer</div>
          <div className="text-sm text-muted">
            {t("system.version")} <span className="font-mono">{info?.version ?? "…"}</span>
            {info?.channel && <> · {channelLabel(info.channel, t)}</>}
            {info?.commit && <> · <span className="font-mono">{info.commit}</span></>}
          </div>
          {info?.commit_date && <div className="text-xs text-muted">{t("system.released")}: {formatDate(info.commit_date, i18n.language)}</div>}
        </div>
      </div>
      <div className="mt-5 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
        <div>
          {t("info.license")}{" "}
          <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noreferrer" className="font-medium text-accent-text hover:underline">
            GNU AGPL-3.0
          </a>
        </div>
        {info?.source_url && (
          <div className="mt-1 text-muted">
            {t("info.source")}{" "}
            <a href={info.source_url} target="_blank" rel="noreferrer" className="font-mono text-accent-text hover:underline">
              {info.source_url.replace(/^https:\/\//, "")}
            </a>
          </div>
        )}
      </div>
      {open && me?.role === "admin" && (
        <div className="mt-6">
          <UpdatePanel compact />
          <div className="mt-4 text-right">
            <Link to="/admin/system" onClick={onClose} className="text-sm font-medium text-accent-text hover:underline">
              {t("info.openSystem")} →
            </Link>
          </div>
        </div>
      )}
    </Dialog>
  );
}
