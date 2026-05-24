import { useState } from "react";
import { Mail, X } from "lucide-react";
import { resendVerification } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useAsyncAction } from "../hooks/useAsyncAction";

const DISMISS_KEY = "content_engine_verify_dismissed";
const RESEND_COOLDOWN_KEY = "content_engine_verify_resend_until";

export function VerificationBanner() {
  const { user } = useAuth();
  const [dismissed, setDismissed] = useState<boolean>(
    () => sessionStorage.getItem(DISMISS_KEY) === "1",
  );

  const resend = useAsyncAction(
    async () => {
      if (!user) return;
      await resendVerification(user.email);
    },
    {
      successMessage: "Verification email sent — check your inbox.",
      cooldownSeconds: 120,
      storageKey: RESEND_COOLDOWN_KEY,
    },
  );

  if (!user || user.email_verified || dismissed) return null;

  function handleDismiss() {
    sessionStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  }

  return (
    <div className="flex items-center justify-between gap-4 px-6 py-3 bg-[color:var(--warning)]/10 border-b border-[color:var(--warning)]/30 text-sm">
      <div className="flex items-center gap-3 min-w-0">
        <Mail className="w-4 h-4 flex-shrink-0 text-[color:var(--warning)]" />
        <div className="min-w-0">
          <span className="text-gray-200">Please verify your email — we sent a link to </span>
          <span className="font-medium text-gray-100 truncate">{user.email}</span>
          <span className="text-gray-400">.</span>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          type="button"
          onClick={() => resend.run()}
          disabled={resend.disabled}
          className="text-xs font-medium text-[color:var(--accent)] hover:underline disabled:opacity-50 disabled:no-underline"
        >
          {resend.running
            ? "Sending…"
            : resend.cooldownSecondsLeft > 0
              ? `Resend (${resend.cooldownSecondsLeft}s)`
              : "Resend email"}
        </button>
        <button
          type="button"
          onClick={handleDismiss}
          className="text-gray-500 hover:text-gray-300"
          aria-label="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
