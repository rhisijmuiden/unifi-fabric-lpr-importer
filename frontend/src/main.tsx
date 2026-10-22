import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import "./i18n";
import { useMe } from "@/lib/auth";
import type { Role } from "@/lib/api";
import { AppLayout } from "@/components/layout/AppLayout";
import { LoginPage } from "@/pages/Login";
import { DashboardPage } from "@/pages/Dashboard";
import { UsersPage } from "@/pages/Users";
import { SsoSettingsPage } from "@/pages/SsoSettings";
import { MailSettingsPage } from "@/pages/MailSettings";
import { SystemPage } from "@/pages/System";
import { AuditPage } from "@/pages/Audit";
import { ConsolesPage } from "@/pages/Consoles";
import { VehiclesPage } from "@/pages/Vehicles";
import { ImportPage } from "@/pages/Import";
import { StatisticsPage } from "@/pages/Statistics";
import { ApiKeysPage } from "@/pages/ApiKeys";
import { setLanguage } from "@/i18n";
import { useEffect } from "react";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { data: me, isLoading } = useMe();
  useEffect(() => {
    if (me) setLanguage(me.language);
  }, [me?.language]); // eslint-disable-line react-hooks/exhaustive-deps
  if (isLoading) return null;
  if (!me) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(me.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <RequireAuth>
                <AppLayout />
              </RequireAuth>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="vehicles" element={<VehiclesPage />} />
            <Route path="consoles" element={<ConsolesPage />} />
            <Route path="import" element={<RequireAuth roles={["admin", "operator"]}><ImportPage /></RequireAuth>} />
            <Route path="statistics" element={<StatisticsPage />} />
            <Route path="admin/api-keys" element={<RequireAuth roles={["admin"]}><ApiKeysPage /></RequireAuth>} />
            <Route path="admin/users" element={<RequireAuth roles={["admin"]}><UsersPage /></RequireAuth>} />
            <Route path="admin/sso" element={<RequireAuth roles={["admin"]}><SsoSettingsPage /></RequireAuth>} />
            <Route path="admin/mail" element={<RequireAuth roles={["admin"]}><MailSettingsPage /></RequireAuth>} />
            <Route path="admin/system" element={<RequireAuth roles={["admin"]}><SystemPage /></RequireAuth>} />
            <Route path="admin/audit" element={<RequireAuth roles={["admin", "operator"]}><AuditPage /></RequireAuth>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
