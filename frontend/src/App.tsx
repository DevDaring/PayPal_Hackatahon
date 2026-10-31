import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { useSession } from "./lib/session";
import { LoginPage } from "./pages/Login";

const Overview = lazy(() => import("./pages/Overview"));
const Requests = lazy(() => import("./pages/Requests"));
const NewRequest = lazy(() => import("./pages/NewRequest"));
const RequestWorkspace = lazy(() => import("./pages/RequestWorkspace"));
const EvidenceDesk = lazy(() => import("./pages/EvidenceDesk"));
const Payments = lazy(() => import("./pages/Payments"));
const PaymentPage = lazy(() => import("./pages/PaymentPage"));
const DemoLab = lazy(() => import("./pages/DemoLab"));
const Evaluation = lazy(() => import("./pages/Evaluation"));
const SettingsPage = lazy(() => import("./pages/Settings"));

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { me, loading } = useSession();
  const loc = useLocation();
  if (loading) return <div className="grid min-h-screen place-items-center"><Spinner label="Opening QuoteGuard…" /></div>;
  if (!me) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Suspense fallback={<div className="p-8"><Spinner /></div>}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Overview />} />
          <Route path="requests" element={<Requests />} />
          <Route path="requests/new" element={<NewRequest />} />
          <Route path="requests/:id" element={<RequestWorkspace />} />
          <Route path="requests/:id/:step" element={<RequestWorkspace />} />
          <Route path="evidence" element={<EvidenceDesk />} />
          <Route path="payments" element={<Payments />} />
          <Route path="payments/:id" element={<PaymentPage />} />
          <Route path="demo-lab" element={<DemoLab />} />
          <Route path="evaluation" element={<Evaluation />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
