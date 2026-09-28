import { useId, useState, type FormEvent, type ReactNode } from "react";

import { ApiError } from "../../api";

export const MIN_PASSWORD_LENGTH = 8;

/** What to tell the user for an error from the auth endpoints. */
export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) return "Check your email address and password.";
    if (error.status > 0 && error.status < 500) return error.message;
  }
  return "We couldn't reach the server. Check your connection and try again.";
}

interface AuthFormProps {
  title: string;
  subtitle: string;
  submitLabel: string;
  pendingLabel: string;
  mode: "login" | "signup";
  pending: boolean;
  error: unknown;
  onSubmit: (email: string, password: string) => void;
  footer: ReactNode;
}

export function AuthForm({ title, subtitle, submitLabel, pendingLabel, mode, pending, error, onSubmit, footer }: AuthFormProps) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const signingUp = mode === "signup";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setProblem("Enter a valid email address.");
      return;
    }
    if (signingUp && password.length < MIN_PASSWORD_LENGTH) {
      setProblem(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`);
      return;
    }
    if (!password) {
      setProblem("Enter your password.");
      return;
    }
    setProblem(null);
    onSubmit(email.trim(), password);
  }

  const message = problem ?? (error ? authErrorMessage(error) : null);
  const inputClass =
    "w-full rounded-lg border border-border bg-bg px-3 py-2 text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40";

  return (
    <div className="mx-auto w-full max-w-sm py-8">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-ink-muted">{subtitle}</p>
      <form noValidate onSubmit={submit} className="mt-6 space-y-4 rounded-xl border border-border bg-surface p-5" aria-describedby={message ? `${id}-error` : undefined}>
        <div className="space-y-1.5">
          <label htmlFor={`${id}-email`} className="text-sm font-medium">Email</label>
          <input
            id={`${id}-email`}
            type="email"
            autoComplete="email"
            inputMode="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
            required
          />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between">
            <label htmlFor={`${id}-password`} className="text-sm font-medium">Password</label>
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-pressed={showPassword}
              aria-controls={`${id}-password`}
              className="text-xs font-medium text-ink-muted hover:text-ink"
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          <input
            id={`${id}-password`}
            type={showPassword ? "text" : "password"}
            autoComplete={signingUp ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-describedby={signingUp ? `${id}-password-hint` : undefined}
            className={inputClass}
            required
            minLength={signingUp ? MIN_PASSWORD_LENGTH : undefined}
          />
          {signingUp && (
            <p id={`${id}-password-hint`} className="text-xs text-ink-muted">At least {MIN_PASSWORD_LENGTH} characters.</p>
          )}
        </div>
        {message && (
          <p id={`${id}-error`} role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
            {message}
          </p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-lg bg-accent px-5 py-2.5 font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? pendingLabel : submitLabel}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-ink-muted">{footer}</p>
    </div>
  );
}
