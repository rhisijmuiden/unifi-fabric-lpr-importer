import { useTranslation } from "react-i18next";
import type { BackupSchedule } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Field, Input, Select, Switch } from "@/components/ui/form";

const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];
const MINUTES = ["00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"];

/** Frequency, day and time of a recurring task (backups, scheduled imports, console scans). */
export function ScheduleEditor({ label, description, value, next, onChange }: { label: string; description?: string; value: BackupSchedule; next: string | null; onChange: (v: BackupSchedule) => void }) {
  const { t, i18n } = useTranslation();
  const set = <K extends keyof BackupSchedule>(k: K, v: BackupSchedule[K]) => onChange({ ...value, [k]: v });
  const weekday = (d: number) => new Date(2026, 9, 19 + d).toLocaleDateString(i18n.language === "nl" ? "nl-NL" : "en-GB", { weekday: "long" });
  return (
    <div className="rounded-lg border border-line p-4">
      <Switch checked={value.enabled} onChange={(v) => set("enabled", v)} label={label} description={description} />
      {value.enabled && (
        <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
          <Field label={t("backup.schedule.frequency")}>
            <Select value={value.frequency} onChange={(e) => set("frequency", e.target.value as BackupSchedule["frequency"])}>
              {(["hourly", "daily", "weekly", "monthly"] as const).map((f) => (
                <option key={f} value={f}>
                  {t(`backup.schedule.${f}`)}
                </option>
              ))}
            </Select>
          </Field>
          {value.frequency === "weekly" && (
            <Field label={t("backup.schedule.weekday")}>
              <Select value={value.weekday} onChange={(e) => set("weekday", Number(e.target.value))}>
                {WEEKDAYS.map((d) => (
                  <option key={d} value={d}>
                    {weekday(d)}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {value.frequency === "monthly" && (
            <Field label={t("backup.schedule.monthday")}>
              <Select value={value.monthday} onChange={(e) => set("monthday", Number(e.target.value))}>
                {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {value.frequency === "hourly" ? (
            <Field label={t("backup.schedule.minute")}>
              <Select value={value.time.slice(3)} onChange={(e) => set("time", `00:${e.target.value}`)}>
                {MINUTES.map((m) => (
                  <option key={m} value={m}>
                    :{m}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <Field label={t("backup.schedule.time")}>
              <Input type="time" value={value.time} onChange={(e) => set("time", e.target.value || "02:00")} />
            </Field>
          )}
          {next && <div className="col-span-full text-xs text-muted">{t("backup.schedule.next", { date: formatDate(next, i18n.language) })}</div>}
        </div>
      )}
    </div>
  );
}
