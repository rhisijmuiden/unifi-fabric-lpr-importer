import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import nl from "./locales/nl.json";

const stored = (() => {
  try {
    return localStorage.getItem("lang");
  } catch {
    return null;
  }
})();

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, nl: { translation: nl } },
  lng: stored === "nl" ? "nl" : "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnObjects: true,
});

export function setLanguage(lang: "en" | "nl") {
  i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
  try {
    localStorage.setItem("lang", lang);
  } catch {
    /* storage unavailable */
  }
}

export default i18n;
