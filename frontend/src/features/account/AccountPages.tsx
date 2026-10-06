import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import {
  useDeleteAccount,
  useRequestPasswordReset,
  useResendVerification,
  useResetPassword,
  useSession,
  useVerifyEmail,
} from "../../api/session";
import { authErrorMessage, MIN_PASSWORD_LENGTH } from "../auth/AuthForm";

const inputClass =
  "w-full rounded-lg border border-border bg-bg px-3 py-2 text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40";
const primaryButton =
  "w-full rounded-lg bg-accent px-5 py-2.5 font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50";

function Page({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-sm py-8">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-2 text-ink-muted">{subtitle}</p>}
      <div className="mt-6">{children}</div>
    </div>
  );
}

function ErrorText({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
      {children}
    </p>
  );
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <div role="status" className="rounded-xl border border-border bg-surface p-5">
      {children}
    </div>
  );
}

/**
 * The token from an emailed link, read once and then removed from the address bar,
 * so it doesn't linger in history or get shared by copying the URL.
 */
function useLinkToken(): string | null {
  const [params] = useSearchParams();
  const [token] = useState(() => params.get("token"));
  useEffect(() => {
    if (token && window.location.search.includes("token=")) {
      window.history.replaceState(window.history.state, "", window.location.pathname);
    }
  }, [token]);
  return token;
}

function PasswordInput({ id, label, value, onChange, autoComplete }: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm font-medium">{label}</label>
        <button
          type="button"
          onClick={() => setShow((v) => !v)}
          aria-pressed={show}
          aria-controls={id}
          className="text-xs font-medium text-ink-muted hover:text-ink"
        >
          {show ? "Hide" : "Show"}
        </button>
      </div>
      <input
        id={id}
        type={show ? "text" : "password"}
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={inputClass}
        required
      />
    </div>
  );
}

export function ForgotPasswordPage() {
  const id = useId();
  const [email, setEmail] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const reset = useRequestPasswordReset();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setProblem("Enter a valid email address.");
      return;
    }
    setProblem(null);
    reset.mutate(email.trim());
  }

  if (reset.isSuccess) {
    return (
      <Page title="Check your email">
        <Notice>
          <p>
            If <strong className="break-all">{email.trim()}</strong> has an account, we've sent it a link to choose a
            new password. The link works for 1 hour.
          </p>
          <p className="mt-3 text-sm text-ink-muted">Nothing arrived? Check your spam folder, or try again in a few minutes.</p>
        </Notice>
        <p className="mt-4 text-center text-sm">
          <Link to="/login" className="font-medium text-accent underline">Back to sign in</Link>
        </p>
      </Page>
    );
  }

  const message = problem ?? (reset.error ? authErrorMessage(reset.error) : null);
  return (
    <Page title="Reset your password" subtitle="Enter your account's email and we'll send you a link to choose a new password.">
      <form noValidate onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-surface p-5">
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
        {message && <ErrorText>{message}</ErrorText>}
        <button type="submit" disabled={reset.isPending} className={primaryButton}>
          {reset.isPending ? "Sending…" : "Send reset link"}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-ink-muted">
        Remembered it? <Link to="/login" className="font-medium text-accent underline">Sign in</Link>
      </p>
    </Page>
  );
}

export function ResetPasswordPage() {
  const id = useId();
  const token = useLinkToken();
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const reset = useResetPassword();

  if (!token) {
    return (
      <Page title="This link is incomplete">
        <Notice>
          <p>Open the link from the email again, or request a new one.</p>
        </Notice>
        <p className="mt-4 text-center text-sm">
          <Link to="/forgot-password" className="font-medium text-accent underline">Request a new link</Link>
        </p>
      </Page>
    );
  }

  if (reset.isSuccess) {
    return (
      <Page title="Password changed">
        <Notice>
          <p>Your new password is set, and every device has been signed out.</p>
        </Notice>
        <Link to="/login" className={`${primaryButton} mt-4 block text-center`}>Sign in</Link>
      </Page>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setProblem(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`);
      return;
    }
    setProblem(null);
    reset.mutate({ token: token!, password });
  }

  const expired = reset.error && authErrorMessage(reset.error).includes("expired");
  const message = problem ?? (reset.error ? authErrorMessage(reset.error) : null);
  return (
    <Page title="Choose a new password">
      <form noValidate onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-surface p-5">
        <PasswordInput
          id={`${id}-password`}
          label="New password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
        />
        <p className="-mt-2 text-xs text-ink-muted">At least {MIN_PASSWORD_LENGTH} characters.</p>
        {message && <ErrorText>{message}</ErrorText>}
        <button type="submit" disabled={reset.isPending} className={primaryButton}>
          {reset.isPending ? "Saving…" : "Set new password"}
        </button>
      </form>
      {expired && (
        <p className="mt-4 text-center text-sm">
          <Link to="/forgot-password" className="font-medium text-accent underline">Request a new link</Link>
        </p>
      )}
    </Page>
  );
}

export function VerifyEmailPage() {
  const token = useLinkToken();
  const verify = useVerifyEmail();
  const session = useSession();
  const started = useRef(false);

  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      verify.mutate(token);
    }
  }, [token, verify]);

  if (!token || verify.isError) {
    return (
      <Page title="We couldn't confirm your email">
        <Notice>
          <p>{verify.error ? authErrorMessage(verify.error) : "This link is incomplete. Open it from the email again."}</p>
          {session.data && !session.data.email_verified && (
            <p className="mt-3 text-sm text-ink-muted">You can send a new link from your account page.</p>
          )}
        </Notice>
        <p className="mt-4 text-center text-sm">
          <Link to={session.data ? "/account" : "/login"} className="font-medium text-accent underline">
            {session.data ? "Go to your account" : "Sign in"}
          </Link>
        </p>
      </Page>
    );
  }

  if (verify.isSuccess) {
    return (
      <Page title="Email confirmed">
        <Notice>
          <p>Thanks. You're all set to analyze your serve.</p>
        </Notice>
        <Link to={session.data ? "/" : "/login"} className={`${primaryButton} mt-4 block text-center`}>
          {session.data ? "Analyze a serve" : "Sign in"}
        </Link>
      </Page>
    );
  }

  return (
    <Page title="Confirming your email…">
      <p role="status" className="text-ink-muted">One moment.</p>
    </Page>
  );
}

/** Shown while the signed-in user hasn't confirmed their email. */
export function VerifyEmailBanner() {
  const session = useSession();
  const resend = useResendVerification();
  const user = session.data;
  if (!user || user.email_verified) return null;
  return (
    <div role="region" aria-label="Confirm your email" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn/40 bg-warn/10 px-4 py-3">
      <p className="text-sm">
        <strong>Confirm your email to start analyzing.</strong>{" "}
        <span className="text-ink-muted">We sent a link to <span className="break-all">{user.email}</span>.</span>
      </p>
      {resend.isSuccess ? (
        <p role="status" className="text-sm text-ink-muted">New link sent.</p>
      ) : (
        <button
          type="button"
          onClick={() => resend.mutate()}
          disabled={resend.isPending}
          className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-2 disabled:opacity-50"
        >
          {resend.isPending ? "Sending…" : "Resend link"}
        </button>
      )}
      {resend.error && <p role="alert" className="w-full text-sm text-bad">{authErrorMessage(resend.error)}</p>}
    </div>
  );
}

function DeleteAccount() {
  const id = useId();
  const navigate = useNavigate();
  const remove = useDeleteAccount(() => navigate("/account-deleted", { replace: true }));
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [typed, setTyped] = useState("");
  const confirmed = typed.trim().toUpperCase() === "DELETE";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!confirmed || !password) return;
    remove.mutate(password);
  }

  return (
    <section aria-labelledby={`${id}-title`} className="space-y-3 rounded-xl border border-bad/40 bg-surface p-5">
      <h2 id={`${id}-title`} className="font-semibold">Delete account</h2>
      <p className="text-sm text-ink-muted">
        Permanently deletes your account and every video and analysis in it. This can't be undone.
      </p>
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-lg border border-bad/60 px-4 py-2 text-sm font-semibold text-bad hover:bg-bad/10"
        >
          Delete my account…
        </button>
      ) : (
        <form noValidate onSubmit={submit} className="space-y-4">
          <PasswordInput
            id={`${id}-password`}
            label="Your password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
          />
          <div className="space-y-1.5">
            <label htmlFor={`${id}-confirm`} className="text-sm font-medium">
              Type <span className="font-mono">DELETE</span> to confirm
            </label>
            <input
              id={`${id}-confirm`}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              className={inputClass}
            />
          </div>
          {remove.error && <ErrorText>{authErrorMessage(remove.error)}</ErrorText>}
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={!confirmed || !password || remove.isPending}
              className="rounded-lg bg-bad px-4 py-2 text-sm font-semibold text-on-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              {remove.isPending ? "Deleting…" : "Permanently delete account"}
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setPassword("");
                setTyped("");
                remove.reset();
              }}
              className="rounded-lg px-4 py-2 text-sm text-ink-muted hover:text-ink"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export function AccountPage() {
  const session = useSession();
  const user = session.data;
  if (!user) return null;
  return (
    <div className="mx-auto w-full max-w-xl space-y-6 py-4">
      <h1 className="text-2xl font-semibold tracking-tight">Account</h1>
      <VerifyEmailBanner />
      <section className="space-y-2 rounded-xl border border-border bg-surface p-5">
        <h2 className="font-semibold">Sign-in details</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-ink-muted">Email</dt>
          <dd className="break-all">
            {user.email} {user.email_verified ? <span className="text-good">· confirmed</span> : <span className="text-warn">· not confirmed</span>}
          </dd>
          <dt className="text-ink-muted">Member since</dt>
          <dd>{new Date(user.created_at).toLocaleDateString(undefined, { dateStyle: "medium" })}</dd>
        </dl>
        <p className="pt-2 text-sm">
          <Link to="/forgot-password" className="font-medium text-accent underline">Change your password</Link>
          <span className="text-ink-muted"> (we'll email you a link)</span>
        </p>
      </section>
      <DeleteAccount />
    </div>
  );
}

export function AccountDeletedPage() {
  return (
    <Page title="Account deleted">
      <Notice>
        <p>Your account and all of its videos and analyses have been deleted.</p>
      </Notice>
      <p className="mt-4 text-center text-sm">
        <Link to="/signup" className="font-medium text-accent underline">Create a new account</Link>
      </p>
    </Page>
  );
}
