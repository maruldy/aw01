import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Activity, AlertTriangle, BookOpen, Globe, Radio, Settings2, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { getProfiles } from "../lib/api";
import { useTranslation, type Locale } from "../lib/i18n";
import type { TranslationKey } from "../locales/ko";

const navItems: { to: string; labelKey: TranslationKey; icon: typeof Sparkles }[] = [
  { to: "/", labelKey: "nav.inbox", icon: Sparkles },
  { to: "/runs", labelKey: "nav.runs", icon: Radio },
  { to: "/knowledge", labelKey: "nav.knowledge", icon: BookOpen },
  { to: "/settings", labelKey: "nav.settings", icon: Settings2 }
];

export function NavShell({ children }: { children: ReactNode }) {
  const { t, locale, setLocale } = useTranslation();
  const [disconnected, setDisconnected] = useState<string[]>([]);

  useEffect(() => {
    getProfiles()
      .then((data) => {
        const names = data.profiles
          .filter((p) => !p.configured)
          .map((p) => p.source);
        setDisconnected(names);
      })
      .catch(() => {});
  }, []);

  function toggleLocale() {
    setLocale(locale === "ko" ? "en" : "ko" as Locale);
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top_left,rgba(196,91,50,0.14),transparent_32%),radial-gradient(circle_at_top_right,rgba(15,92,99,0.12),transparent_34%)]" />
      <div className="mx-auto flex min-h-screen max-w-[1600px] gap-6 px-4 py-5 lg:px-6">
        <aside className="sticky top-5 hidden h-[calc(100vh-2.5rem)] w-72 shrink-0 flex-col rounded-[28px] border border-black/5 bg-white/70 p-5 shadow-panel backdrop-blur xl:flex">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ink text-canvas">
                <Activity className="h-6 w-6" />
              </div>
              <div>
                <p className="font-display text-lg font-semibold">{t("nav.title")}</p>
                <p className="text-sm text-ink/60">{t("nav.subtitle")}</p>
              </div>
            </Link>
            <button
              type="button"
              onClick={toggleLocale}
              className="flex h-8 w-8 items-center justify-center rounded-xl bg-sand/60 text-ink/70 transition hover:bg-sand hover:text-ink"
              title={t("lang.switch")}
            >
              <Globe className="h-4 w-4" />
            </button>
          </div>

          <nav className="mt-8 space-y-2">
            {navItems.map(({ to, labelKey, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-2xl px-4 py-3 transition ${
                    isActive ? "bg-ink text-canvas" : "bg-transparent text-ink/70 hover:bg-sand/50 hover:text-ink"
                  }`
                }
              >
                <Icon className="h-4 w-4" />
                <span className="font-medium">{t(labelKey)}</span>
              </NavLink>
            ))}
          </nav>

          {disconnected.length > 0 ? (
            <Link
              to="/settings"
              className="mt-4 flex items-start gap-2.5 rounded-[18px] border border-signal/20 bg-signal/5 px-4 py-3 transition hover:bg-signal/10"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-signal" />
              <p className="text-xs leading-5 text-ink/70">
                <span className="font-semibold text-signal">{disconnected.join(", ")}</span>
                {" "}{t("nav.disconnectedHint")}
              </p>
            </Link>
          ) : null}

          <div className="mt-auto rounded-[24px] bg-ink p-5 text-canvas">
            <p className="font-display text-lg">{t("nav.pushFirst")}</p>
            <p className="mt-2 text-sm text-canvas/70">
              {t("nav.pushFirstDesc")}
            </p>
          </div>
        </aside>

        <main className="flex-1 animate-fade-up">{children}</main>
      </div>
    </div>
  );
}
