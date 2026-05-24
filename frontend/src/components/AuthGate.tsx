import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { getMe } from "../lib/api";
import { clearToken, updateStoredUser, useAuth } from "../lib/auth";

type GateStatus = "checking" | "ready" | "invalid" | "unverified";

/** Validates the stored token with /auth/me before rendering protected UI or firing API queries. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { token, isAuthenticated, isVerified } = useAuth();
  const [status, setStatus] = useState<GateStatus>(() => (token ? "checking" : "ready"));

  useEffect(() => {
    if (!token) {
      setStatus("ready");
      return;
    }

    let cancelled = false;
    setStatus("checking");

    getMe()
      .then((user) => {
        if (cancelled) return;
        updateStoredUser(user);
        setStatus(user.email_verified ? "ready" : "unverified");
      })
      .catch(() => {
        if (cancelled) return;
        clearToken();
        setStatus("invalid");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "checking") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-gray-950">
        <Loader2 className="w-7 h-7 text-gray-500 animate-spin" aria-hidden />
        <p className="text-sm text-gray-500">Loading your workspace…</p>
      </div>
    );
  }

  if (status === "invalid" || !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (status === "unverified" || !isVerified) {
    return <Navigate to="/verify-email-required" replace />;
  }

  return <>{children}</>;
}
