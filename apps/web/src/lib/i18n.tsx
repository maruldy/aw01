import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

import ko, { type TranslationKey } from "../locales/ko";
import en from "../locales/en";

export type Locale = "ko" | "en";

const translations: Record<Locale, Record<TranslationKey, string>> = { ko, en };

interface I18nContextValue {
  locale: Locale;
  t: (key: TranslationKey) => string;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nContextValue>({
  locale: "ko",
  t: (key) => ko[key],
  setLocale: () => {},
});

const STORAGE_KEY = "wh_locale";

function getInitialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "ko" || stored === "en") return stored;
  return "ko";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const t = useCallback(
    (key: TranslationKey) => translations[locale][key] ?? key,
    [locale],
  );

  return (
    <I18nContext.Provider value={{ locale, t, setLocale }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useTranslation() {
  return useContext(I18nContext);
}
