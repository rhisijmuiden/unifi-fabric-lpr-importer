import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value: string | null | undefined, locale: string) {
  if (!value) return "–";
  return new Date(value).toLocaleString(locale === "nl" ? "nl-NL" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** Human name for a release branch; other branches (development) show as-is. */
export function channelLabel(channel: string | null | undefined, t: (key: string) => string) {
  if (channel === "main") return t("system.production");
  if (channel === "test") return t("system.test");
  return channel ?? "–";
}
