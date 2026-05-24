import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthExpiredListener } from "./components/AuthExpiredListener";
import { AuthGate } from "./components/AuthGate";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import Admin from "./pages/Admin";
import Analytics from "./pages/Analytics";
import Calendar from "./pages/Calendar";
import Compose from "./pages/Compose";
import Dashboard from "./pages/Dashboard";
import Engagement from "./pages/Engagement";
import Library from "./pages/Library";
import Login from "./pages/Login";
import Notifications from "./pages/Notifications";
import Research from "./pages/Research";
import Settings from "./pages/Settings";
import Signup from "./pages/Signup";
import VerifyEmail from "./pages/VerifyEmail";
import VerifyEmailRequired from "./pages/VerifyEmailRequired";
import { useAuth } from "./lib/auth";

function AdminOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthExpiredListener />
        <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/verify-email-required" element={<VerifyEmailRequired />} />

        <Route
          path="/"
          element={
            <AuthGate>
              <Layout />
            </AuthGate>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="calendar" element={<Calendar />} />
          <Route path="library" element={<Library />} />
          <Route path="research" element={<Research />} />
          <Route path="engagement" element={<Engagement />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="compose" element={<Compose />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="settings" element={<Settings />} />
          <Route
            path="admin"
            element={
              <AdminOnly>
                <Admin />
              </AdminOnly>
            }
          />
        </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
