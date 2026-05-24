import { Navigate, useNavigate } from "react-router-dom";
import { Mail, LogOut } from "lucide-react";
import { resendVerification } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Logo } from "../components/Logo";
import { useAsyncAction } from "../hooks/useAsyncAction";

const RESEND_COOLDOWN_KEY = "content_engine_verify_resend_until";

export default function VerifyEmailRequired() {
  const navigate = useNavigate();
  const { user, isAuthenticated, isVerified, logout } = useAuth();

  const resend = useAsyncAction(
    async () => {
      if (!user) return;
      await resendVerification(user.email);
    },
    {
      successMessage: "A fresh verification email was sent. Check your inbox.",
      cooldownSeconds: 120,
      storageKey: RESEND_COOLDOWN_KEY,
    },
  );

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (isVerified) return <Navigate to="/" replace />;

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 text-gray-100 px-4">
      <div className="w-full max-w-md text-center">
        <div className="flex justify-center mb-6">
          <Logo size={44} className="text-gray-400" />
        </div>
        <Mail className="w-12 h-12 mx-auto mb-4 text-[color:var(--accent)]" />
        <h1 className="text-xl font-semibold mb-2">Verify your email to continue</h1>
        <p className="text-sm text-gray-400 mb-6">
          We sent a verification link to{" "}
          <span className="text-gray-200 font-medium">{user?.email}</span>.
          Open that link before using Content Engine.
        </p>

        <div className="space-y-3">
          <button
            type="button"
            onClick={() => resend.run()}
            disabled={resend.disabled}
            className="w-full bg-[color:var(--accent)] hover:bg-[color:var(--accent-hover)] disabled:opacity-50 text-[color:var(--text-inverse)] text-sm font-medium rounded px-4 py-2 transition"
          >
            {resend.running
              ? "Sending…"
              : resend.cooldownSecondsLeft > 0
                ? `Wait ${resend.cooldownSecondsLeft}s to resend`
                : "Resend verification email"}
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 text-sm text-gray-400 hover:text-gray-100 px-4 py-2 transition"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
