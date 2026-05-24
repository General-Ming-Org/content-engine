import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import { ApiError, verifyEmail } from "../lib/api";
import { updateStoredUser, useAuth } from "../lib/auth";
import { Logo } from "../components/Logo";

type State =
  | { kind: "loading" }
  | { kind: "success"; email: string }
  | { kind: "error"; message: string }
  | { kind: "missing" };

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const token = params.get("token");
  const [state, setState] = useState<State>(() =>
    token ? { kind: "loading" } : { kind: "missing" },
  );
  // Single-use tokens: StrictMode fires effects twice in dev, which would consume
  // the token on the first call and 400 on the second. We share one in-flight
  // promise across mounts (keyed by token) so the API is only called once, and
  // both mounts await the same result.
  const requestRef = useRef<{ token: string; promise: ReturnType<typeof verifyEmail> } | null>(
    null,
  );

  useEffect(() => {
    if (!token) return;
    if (!requestRef.current || requestRef.current.token !== token) {
      requestRef.current = { token, promise: verifyEmail(token) };
    }
    const promise = requestRef.current.promise;
    let cancelled = false;
    (async () => {
      try {
        const verified = await promise;
        if (cancelled) return;
        setState({ kind: "success", email: verified.email });

        // Merge into stored session so route guards immediately unlock the app
        // if the user is already signed in on this device.
        const raw = localStorage.getItem("content_engine_user");
        if (raw) {
          updateStoredUser({ ...JSON.parse(raw), email_verified: true });
        }
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Couldn't verify this link. Please request a new one.";
        setState({ kind: "error", message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-md text-center">
        <div className="flex justify-center mb-6">
          <Logo size={44} className="text-gray-400" />
        </div>

        {state.kind === "loading" && (
          <>
            <Loader2 className="w-10 h-10 mx-auto mb-4 text-[color:var(--accent)] animate-spin" />
            <h1 className="text-xl font-semibold text-gray-100 mb-2">Verifying your email…</h1>
            <p className="text-sm text-gray-400">This only takes a moment.</p>
          </>
        )}

        {state.kind === "success" && (
          <>
            <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-[color:var(--success)]" />
            <h1 className="text-xl font-semibold text-gray-100 mb-2">Email verified</h1>
            <p className="text-sm text-gray-400 mb-8">
              <span className="text-gray-200">{state.email}</span> is now confirmed.
            </p>
            <Link
              to={user ? "/" : "/login"}
              className="inline-block px-5 py-2 rounded-lg bg-[color:var(--accent)] hover:bg-[color:var(--accent-hover)] text-[color:var(--text-inverse)] text-sm font-medium"
            >
              {user ? "Continue to dashboard" : "Sign in"}
            </Link>
          </>
        )}

        {state.kind === "error" && (
          <>
            <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-[color:var(--warning)]" />
            <h1 className="text-xl font-semibold text-gray-100 mb-2">Verification failed</h1>
            <p className="text-sm text-gray-400 mb-6">{state.message}</p>
            <Link to={user ? "/verify-email-required" : "/login"} className="text-sm text-[color:var(--accent)] hover:underline">
              {user ? "Back to verification" : "Back to sign in"}
            </Link>
          </>
        )}

        {state.kind === "missing" && (
          <>
            <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-[color:var(--warning)]" />
            <h1 className="text-xl font-semibold text-gray-100 mb-2">Missing verification token</h1>
            <p className="text-sm text-gray-400 mb-6">
              Open the link from your verification email to verify your account.
            </p>
            <Link to={user ? "/verify-email-required" : "/login"} className="text-sm text-[color:var(--accent)] hover:underline">
              {user ? "Back to verification" : "Back to sign in"}
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
