import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, login } from "../lib/api";
import { setSession } from "../lib/auth";
import { Logo } from "../components/Logo";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await login(email, password);
      setSession(res.access_token, res.user);
      navigate(res.user.email_verified ? "/" : "/verify-email-required");
    } catch (err) {
      if (err instanceof ApiError) {
        // Status-specific friendlier text where appropriate.
        if (err.status === 0) {
          setError("Can't reach the server. Check your connection and try again.");
        } else if (err.status === 401) {
          setError("Email or password is incorrect. Please try again.");
        } else if (err.status === 403) {
          setError(err.message || "This account has been disabled.");
        } else if (err.status === 429) {
          setError("Too many sign-in attempts — wait a moment and try again.");
        } else {
          setError(err.message);
        }
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 text-gray-100 px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8">
          <Logo size={32} className="text-gray-400" />
          <span className="text-lg font-semibold text-gray-100">Content Engine</span>
        </div>

        <h1 className="text-2xl font-semibold mb-1">Sign in</h1>
        <p className="text-sm text-gray-400 mb-8">Welcome back.</p>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label className="block text-xs uppercase tracking-wide text-gray-500 mb-1.5">
              Email
            </label>
            <input
              type="email"
              required
              autoFocus
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-gray-900 border border-gray-800 rounded px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)]"
            />
          </div>

          <div>
            <label className="block text-xs uppercase tracking-wide text-gray-500 mb-1.5">
              Password
            </label>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-900 border border-gray-800 rounded px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)]"
            />
          </div>

          {error && (
            <div
              role="alert"
              className="text-sm text-[color:var(--danger)] bg-[color:var(--danger)]/10 border border-[color:var(--danger)]/30 rounded px-3 py-2"
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[color:var(--accent)] hover:bg-[color:var(--accent-hover)] disabled:opacity-50 text-[color:var(--text-inverse)] text-sm font-medium rounded px-4 py-2 transition"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-sm text-gray-500 mt-6 text-center">
          No account?{" "}
          <Link to="/signup" className="text-[color:var(--accent)] hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
