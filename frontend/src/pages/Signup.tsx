import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { ApiError, signup } from "../lib/api";
import { setSession } from "../lib/auth";
import { Logo } from "../components/Logo";

interface FieldErrors {
  name?: string;
  email?: string;
  password?: string;
  password_confirm?: string;
  form?: string;
}

export default function Signup() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState<{ email: string } | null>(null);

  function validate(): FieldErrors {
    const e: FieldErrors = {};
    if (!name.trim()) e.name = "Please enter your name.";
    if (!email.trim()) e.email = "Please enter your email.";
    if (password.length < 8) e.password = "Password must be at least 8 characters.";
    if (passwordConfirm !== password) e.password_confirm = "Passwords don't match.";
    return e;
  }

  async function handleSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    const v = validate();
    setErrors(v);
    if (Object.keys(v).length) return;

    setLoading(true);
    try {
      const res = await signup(email.trim(), password, passwordConfirm, name.trim());
      setSession(res.access_token, res.user);
      setDone({ email: res.user.email });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setErrors({ email: "An account with this email already exists." });
        } else if (err.status === 422 && Array.isArray((err.detail as any)?.detail)) {
          // Pydantic field errors → map back to inputs.
          const next: FieldErrors = {};
          for (const item of (err.detail as any).detail) {
            const field = item?.loc?.[item.loc.length - 1];
            if (field && typeof field === "string" && field in {
              name: 1, email: 1, password: 1, password_confirm: 1,
            }) {
              (next as any)[field] = item.msg;
            } else {
              next.form = item.msg;
            }
          }
          setErrors(next);
        } else if (err.status === 0) {
          setErrors({ form: "Can't reach the server. Check your connection and try again." });
        } else {
          setErrors({ form: err.message });
        }
      } else {
        setErrors({ form: "Something went wrong. Please try again." });
      }
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950 text-gray-100 px-4">
        <div className="w-full max-w-sm text-center">
          <div className="flex justify-center mb-6">
            <Logo size={36} className="text-gray-400" />
          </div>
          <CheckCircle2 className="w-10 h-10 mx-auto mb-4 text-[color:var(--success)]" />
          <h1 className="text-xl font-semibold mb-2">Check your inbox</h1>
          <p className="text-sm text-gray-400 mb-8">
            We sent a verification link to <span className="text-gray-200">{done.email}</span>.
            You must verify this email before using Content Engine.
          </p>
          <button
            onClick={() => navigate("/verify-email-required")}
            className="w-full bg-[color:var(--accent)] hover:bg-[color:var(--accent-hover)] text-[color:var(--text-inverse)] text-sm font-medium rounded px-4 py-2 transition"
          >
            Continue
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 text-gray-100 px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8">
          <Logo size={32} className="text-gray-400" />
          <span className="text-lg font-semibold text-gray-100">Content Engine</span>
        </div>

        <h1 className="text-2xl font-semibold mb-1">Create account</h1>
        <p className="text-sm text-gray-400 mb-8">The first account becomes admin.</p>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <Field label="Name" error={errors.name}>
            <input
              type="text"
              required
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputCls(!!errors.name)}
            />
          </Field>

          <Field label="Email" error={errors.email}>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputCls(!!errors.email)}
            />
          </Field>

          <Field
            label="Password"
            error={errors.password}
            hint="8+ characters"
          >
            <input
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputCls(!!errors.password)}
            />
          </Field>

          <Field label="Confirm password" error={errors.password_confirm}>
            <input
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              className={inputCls(!!errors.password_confirm)}
            />
          </Field>

          {errors.form && (
            <div
              role="alert"
              className="text-sm text-[color:var(--danger)] bg-[color:var(--danger)]/10 border border-[color:var(--danger)]/30 rounded px-3 py-2"
            >
              {errors.form}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[color:var(--accent)] hover:bg-[color:var(--accent-hover)] disabled:opacity-50 text-[color:var(--text-inverse)] text-sm font-medium rounded px-4 py-2 transition"
          >
            {loading ? "Creating…" : "Create account"}
          </button>
        </form>

        <p className="text-sm text-gray-500 mt-6 text-center">
          Already have one?{" "}
          <Link to="/login" className="text-[color:var(--accent)] hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs uppercase tracking-wide text-gray-500 mb-1.5">
        {label}
        {hint && <span className="ml-2 text-gray-600 normal-case">{hint}</span>}
      </label>
      {children}
      {error && (
        <p className="text-xs text-[color:var(--danger)] mt-1">{error}</p>
      )}
    </div>
  );
}

function inputCls(invalid: boolean) {
  return [
    "w-full bg-gray-900 border rounded px-3 py-2 text-sm focus:outline-none",
    invalid
      ? "border-[color:var(--danger)] focus:border-[color:var(--danger)]"
      : "border-gray-800 focus:border-[color:var(--accent)]",
  ].join(" ");
}
