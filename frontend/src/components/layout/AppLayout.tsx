import { useState, type ComponentType } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  BarChart3,
  Car,
  DatabaseBackup,
  FileUp,
  Info,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Mail,
  Menu,
  Moon,
  PlugZap,
  RefreshCw,
  ScrollText,
  Server,
  Sun,
  Users,
  X,
} from "lucide-react";
import { useLogout, useMe } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { setLanguage } from "@/i18n";
import { api, type Role } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { InfoDialog } from "@/components/InfoDialog";
import { useSystemInfo } from "@/lib/system";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  roles?: Role[];
}

function useNav(): { title: string; items: NavItem[] }[] {
  const { t } = useTranslation();
  return [
    {
      title: t("nav.overview"),
      items: [
        { to: "/", label: t("nav.dashboard"), icon: LayoutDashboard },
        { to: "/vehicles", label: t("nav.vehicles"), icon: Car },
        { to: "/import", label: t("nav.import"), icon: FileUp, roles: ["admin", "operator"] },
        { to: "/consoles", label: t("nav.consoles"), icon: Server },
        { to: "/statistics", label: t("nav.statistics"), icon: BarChart3 },
      ],
    },
    {
      title: t("nav.administration"),
      items: [
        { to: "/admin/users", label: t("nav.users"), icon: Users, roles: ["admin"] },
        { to: "/admin/api-keys", label: t("nav.apiKeys"), icon: PlugZap, roles: ["admin"] },
        { to: "/admin/sso", label: t("nav.sso"), icon: KeyRound, roles: ["admin"] },
        { to: "/admin/mail", label: t("nav.mail"), icon: Mail, roles: ["admin"] },
        { to: "/admin/backup", label: t("nav.backup"), icon: DatabaseBackup, roles: ["admin"] },
        { to: "/admin/system", label: t("nav.system"), icon: RefreshCw, roles: ["admin"] },
        { to: "/admin/audit", label: t("nav.audit"), icon: ScrollText, roles: ["admin", "operator"] },
      ],
    },
  ];
}

function Logo() {
  return (
    <>
      <img src="/brand/rhis-logo.svg" alt="RHIS" className="h-6 w-auto dark:hidden" />
      <img src="/brand/rhis-logo-wit.svg" alt="RHIS" className="hidden h-6 w-auto dark:block" />
    </>
  );
}

function Sidebar({ onNavigate, onInfo }: { onNavigate?: () => void; onInfo: () => void }) {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const { data: info } = useSystemInfo();
  const groups = useNav();
  return (
    <div className="flex h-full flex-col">
      <div className="px-6 pb-4 pt-6">
        <Logo />
        <div className="mt-3 text-sm font-bold leading-tight">{t("app.name")}</div>
        <div className="text-xs text-muted">{t("app.subtitle")}</div>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {groups.map((group) => {
          const items = group.items.filter((i) => !i.roles || (me && i.roles.includes(me.role)));
          if (!items.length) return null;
          return (
            <div key={group.title}>
              <div className="px-3 pb-2 text-[11px] font-bold uppercase tracking-wider text-muted">{group.title}</div>
              <ul className="space-y-0.5">
                {items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === "/"}
                      onClick={onNavigate}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold transition-colors",
                          isActive ? "bg-nacht text-white dark:bg-lucht/15 dark:text-lucht" : "text-muted hover:bg-surface hover:text-ink",
                        )
                      }
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      <span className="flex-1 truncate">{item.label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </nav>
      <div className="border-t border-line p-3">
        <button
          onClick={onInfo}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm font-semibold text-muted transition-colors hover:bg-surface hover:text-ink"
        >
          <Info className="h-4 w-4" />
          <span className="flex-1">{t("info.button")}</span>
          <span className="font-mono text-xs">{info?.version ? `v${info.version}` : ""}</span>
        </button>
      </div>
    </div>
  );
}

export function AppLayout() {
  const { t, i18n } = useTranslation();
  const { data: me, refetch } = useMe();
  const logout = useLogout();
  const { dark, toggle } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);

  const changeLanguage = async (lang: "en" | "nl") => {
    setLanguage(lang);
    await api("/auth/me/language", { method: "PUT", body: { language: lang } });
    refetch();
  };

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-raised lg:block">
        <Sidebar onInfo={() => setInfoOpen(true)} />
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-nacht/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-raised">
            <button className="absolute right-3 top-6 text-muted" onClick={() => setMobileOpen(false)} aria-label="Close menu">
              <X className="h-5 w-5" />
            </button>
            <Sidebar onNavigate={() => setMobileOpen(false)} onInfo={() => { setMobileOpen(false); setInfoOpen(true); }} />
          </aside>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-2 border-b border-line bg-surface/85 px-4 backdrop-blur sm:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Menu">
            <Menu className="h-5 w-5" />
          </Button>
          <div className="flex-1" />
          <div className="flex rounded-md border border-line bg-raised p-0.5 text-xs font-semibold">
            {(["en", "nl"] as const).map((lang) => (
              <button
                key={lang}
                onClick={() => changeLanguage(lang)}
                className={cn(
                  "rounded-md px-2 py-1 uppercase",
                  i18n.language === lang ? "bg-primary text-primary-ink" : "text-muted hover:text-ink",
                )}
              >
                {lang}
              </button>
            ))}
          </div>
          <Button variant="ghost" size="icon" onClick={toggle} aria-label={t("theme.toggle")}>
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <div className="ml-2 hidden items-center gap-3 border-l border-line pl-4 sm:flex">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-nacht text-sm font-bold text-white ring-2 ring-koraal/70">
              {(me?.display_name || me?.username || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold">{me?.display_name || me?.username}</div>
              <div className="text-xs text-muted">{me && t(`roles.${me.role}`)}</div>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={logout} aria-label={t("userMenu.logout")} title={t("userMenu.logout")}>
            <LogOut className="h-4 w-4" />
          </Button>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
      <InfoDialog open={infoOpen} onClose={() => setInfoOpen(false)} />
    </div>
  );
}
