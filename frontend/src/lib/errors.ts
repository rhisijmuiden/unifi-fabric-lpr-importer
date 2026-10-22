import type { TFunction } from "i18next";
import { ApiError } from "./api";

/** Translate an API error detail using the given namespace, falling back to a generic message. */
export function errorMessage(t: TFunction, err: unknown, ns?: string) {
  const detail = err instanceof ApiError ? err.detail : String(err);
  const base = detail.split(":")[0];
  if (ns) {
    const key = `${ns}.errors.${base}`;
    const translated = t(key);
    if (translated !== key) return translated;
  }
  return t("errors.generic", { detail });
}
