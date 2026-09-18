import { Suspense, lazy, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "@/components/layout/AppLayout";
import { LoadingState } from "@/components/ui";
import { useApplyTheme } from "@/hooks";
import Login from "@/pages/Login";
import { useAuthStore } from "@/store";

// "Chargement lazy des pages" (spec)  un chunk séparé par page plutôt que
// tout regroupé dans le bundle principal (déjà signalé par Vite comme trop
// volumineux, voir avertissement de build).
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const NewObjective = lazy(() => import("@/pages/NewObjective"));
const Campaigns = lazy(() => import("@/pages/Campaigns"));
const AgentControl = lazy(() => import("@/pages/AgentControl"));
const HITLValidation = lazy(() => import("@/pages/HITLValidation"));
const ContentManagement = lazy(() => import("@/pages/ContentManagement"));
const Analytics = lazy(() => import("@/pages/Analytics"));
const Settings = lazy(() => import("@/pages/Settings"));

function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function LazyPage({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingState label="Chargement de la page..." />}>{children}</Suspense>;
}

export default function App() {
  const restoreSession = useAuthStore((s) => s.restoreSession);
  useApplyTheme();

  useEffect(() => {
    restoreSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- exécuté une seule fois au montage.
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            // <RequireAuth>
              <AppLayout />
            // </RequireAuth>
          }
        >
          <Route path="/" element={<LazyPage><Dashboard /></LazyPage>} />
          <Route path="/objectifs" element={<LazyPage><NewObjective /></LazyPage>} />
          <Route path="/campagnes" element={<LazyPage><Campaigns /></LazyPage>} />
          <Route path="/agents" element={<LazyPage><AgentControl /></LazyPage>} />
          <Route path="/validations" element={<LazyPage><HITLValidation /></LazyPage>} />
          <Route path="/contenus" element={<LazyPage><ContentManagement /></LazyPage>} />
          <Route path="/analytics" element={<LazyPage><Analytics /></LazyPage>} />
          <Route path="/settings" element={<LazyPage><Settings /></LazyPage>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
