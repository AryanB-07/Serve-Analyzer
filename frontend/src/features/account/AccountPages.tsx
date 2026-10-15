import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import {
  useConfirmEmailChange,
  useDeleteAccount,
  useDownloadData,
  useRequestEmailChange,
  useRequestPasswordReset,
  useResendVerification,
  useResetPassword,
  useSession,
  useVerifyEmail,
} from "../../api/session";
import { ApiError } from "../../api/client";
import { useBlocks, useUnblock } from "../../api/friends";
import { useChangePassword, useProfile, useUpdateProfile, useUsernameCheck } from "../../api/profile";
import type { ProfileUpdate } from "../../api/types";
import { normaliseUsername, usernameProblem } from "../../lib/username";
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
            <p className="mt-3 text-sm text-ink-muted">You can send a new link from Settings.</p>
          )}
        </Notice>
        <p className="mt-4 text-center text-sm">
          <Link to={session.data ? "/settings" : "/login"} className="font-medium text-accent underline">
            {session.data ? "Go to Settings" : "Sign in"}
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
  const remove = useDeleteAccount(() => navigate("/account-deleted", { replace: true, flushSync: true }));
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
        Permanently deletes your account, your profile and every video and analysis in it. This can't be undone.
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

const secondaryButton =
  "rounded-lg border border-border px-4 py-2 text-sm font-semibold hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50";

function ChangeEmail({ current }: { current: string }) {
  const id = useId();
  const change = useRequestEmailChange();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  function close() {
    setOpen(false);
    setEmail("");
    setPassword("");
    setProblem(null);
    change.reset();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const next = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(next)) return setProblem("Enter a valid email address.");
    if (next.toLowerCase() === current) return setProblem("That's already your email.");
    if (!password) return setProblem("Enter your current password.");
    setProblem(null);
    change.mutate({ newEmail: next, password });
  }

  if (change.isSuccess) {
    return (
      <div role="status" className="space-y-2 rounded-lg border border-border bg-bg p-3 text-sm">
        <p>
          We sent a link to <strong className="break-all">{email.trim()}</strong>. Open it within 24 hours to switch.
          Until then you keep signing in with <span className="break-all">{current}</span>.
        </p>
        <button type="button" onClick={close} className="font-medium text-accent underline">Done</button>
      </div>
    );
  }
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="font-medium text-accent underline">
        Change your email
      </button>
    );
  }
  const message = problem ?? (change.error ? authErrorMessage(change.error) : null);
  return (
    <form noValidate onSubmit={submit} aria-label="Change your email" className="space-y-3 rounded-lg border border-border bg-bg p-3">
      <div className="space-y-1.5">
        <label htmlFor={`${id}-email`} className="text-sm font-medium">New email</label>
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
      <PasswordInput
        id={`${id}-password`}
        label="Current password"
        value={password}
        onChange={setPassword}
        autoComplete="current-password"
      />
      {message && <ErrorText>{message}</ErrorText>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={change.isPending} className={secondaryButton}>
          {change.isPending ? "Sending…" : "Send confirmation link"}
        </button>
        <button type="button" onClick={close} className="rounded-lg px-4 py-2 text-sm text-ink-muted hover:text-ink">
          Cancel
        </button>
      </div>
    </form>
  );
}

function DownloadData() {
  const id = useId();
  const download = useDownloadData();
  return (
    <section aria-labelledby={`${id}-title`} className="space-y-3 rounded-xl border border-border bg-surface p-5">
      <h2 id={`${id}-title`} className="font-semibold">Your data</h2>
      <p className="text-sm text-ink-muted">
        Download everything we store about you as one JSON file: your account details, your profile, and every analysis
        with its results, feedback, note and any problem you reported. It also has links to download your videos and
        profile picture, which work for 6 hours.
      </p>
      <button type="button" onClick={() => download.mutate()} disabled={download.isPending} className={secondaryButton}>
        {download.isPending ? "Preparing…" : "Download my data"}
      </button>
      {download.isSuccess && (
        <p role="status" className="text-sm text-ink-muted">
          Downloaded {download.data.analyses.length} {download.data.analyses.length === 1 ? "analysis" : "analyses"}.
        </p>
      )}
      {download.error && <ErrorText>{authErrorMessage(download.error)}</ErrorText>}
    </section>
  );
}

export function ConfirmEmailChangePage() {
  const token = useLinkToken();
  const confirm = useConfirmEmailChange();
  const session = useSession();
  const started = useRef(false);

  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      confirm.mutate(token);
    }
  }, [token, confirm]);

  if (!token || confirm.isError) {
    return (
      <Page title="We couldn't change your email">
        <Notice>
          <p>{confirm.error ? authErrorMessage(confirm.error) : "This link is incomplete. Open it from the email again."}</p>
          <p className="mt-3 text-sm text-ink-muted">Your account still uses its previous email address.</p>
        </Notice>
        <p className="mt-4 text-center text-sm">
          <Link to={session.data ? "/settings" : "/login"} className="font-medium text-accent underline">
            {session.data ? "Go to Settings" : "Sign in"}
          </Link>
        </p>
      </Page>
    );
  }

  if (confirm.isSuccess) {
    return (
      <Page title="Email changed">
        <Notice>
          <p>
            {session.data ? (
              <>Your account now uses <strong className="break-all">{session.data.email}</strong>.</>
            ) : (
              "Sign in with your new email address from now on."
            )}
          </p>
        </Notice>
        <Link to={session.data ? "/settings" : "/login"} className={`${primaryButton} mt-4 block text-center`}>
          {session.data ? "Go to Settings" : "Sign in"}
        </Link>
      </Page>
    );
  }

  return (
    <Page title="Changing your email…">
      <p role="status" className="text-ink-muted">One moment.</p>
    </Page>
  );
}

const MAX_DISPLAY_NAME = 50;
const MAX_BIO = 300;

/** A message for a failed profile or password change: the API's own words when it gives any. */
function settingsErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status > 0 && error.status < 500) return error.message;
  return authErrorMessage(error);
}

/** The username as it's typed, checked against the rules here, then (after a pause) with the API. */
function useUsernameState(value: string, current: string | null) {
  const name = normaliseUsername(value);
  const [settled, setSettled] = useState(name);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(name), 400);
    return () => clearTimeout(timer);
  }, [name]);
  const local = name ? usernameProblem(name) : null;
  const ask = !name || local || name === current || settled !== name ? null : name;
  const check = useUsernameCheck(ask);
  const answer = check.data && check.data.username === name ? check.data : null;
  let text: ReactNode = "Letters, numbers and underscores, 3 to 20 of them. People who know it can find you and see your name and picture.";
  let tone = "text-ink-muted";
  if (local) [text, tone] = [local, "text-bad"];
  else if (name && name === current) text = "This is your username.";
  else if (answer) [text, tone] = answer.available ? [`@${name} is available.`, "text-good"] : [answer.problem, "text-bad"];
  else if (name) text = "Checking…";
  // Saving waits for the API's answer, and is refused when the name isn't available.
  const usable = name === current || (!local && answer?.available === true);
  return { text, tone, usable };
}

function ProfileSettings() {
  const id = useId();
  const profile = useProfile();
  const save = useUpdateProfile();
  const [form, setForm] = useState<{ username: string; display_name: string; bio: string } | null>(null);
  const [saved, setSaved] = useState(false);
  const p = profile.data;

  useEffect(() => {
    if (p && form === null) setForm({ username: p.username ?? "", display_name: p.display_name ?? "", bio: p.bio ?? "" });
  }, [p, form]);

  const username = useUsernameState(form?.username ?? "", p?.username ?? null);

  if (profile.isError) return <ErrorText>{settingsErrorMessage(profile.error)}</ErrorText>;
  if (!p || !form) return <p className="text-sm text-ink-muted">Loading your profile…</p>;

  const changes: ProfileUpdate = {};
  if (normaliseUsername(form.username) !== (p.username ?? "") && form.username.trim()) changes.username = form.username;
  if (form.display_name.trim() !== (p.display_name ?? "")) changes.display_name = form.display_name;
  if (form.bio.trim() !== (p.bio ?? "")) changes.bio = form.bio;
  const blocked = (changes.username !== undefined && !username.usable) || (p.username !== null && !form.username.trim());

  function set(field: keyof NonNullable<typeof form>, value: string) {
    setSaved(false);
    save.reset();
    setForm((f) => (f ? { ...f, [field]: value } : f));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (blocked || Object.keys(changes).length === 0) return;
    save.mutate(changes, {
      onSuccess: (next) => {
        setForm({ username: next.username ?? "", display_name: next.display_name ?? "", bio: next.bio ?? "" });
        setSaved(true);
      },
    });
  }

  return (
    <section id="profile" aria-labelledby={`${id}-title`} className="scroll-mt-20 space-y-4 rounded-xl border border-border bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id={`${id}-title`} className="font-semibold">Profile</h2>
          <p className="text-sm text-ink-muted">
            {p.username
              ? "People who know your username see your name and picture; friends also see your bio."
              : "Nobody can find you until you choose a username."}
          </p>
        </div>
        <Link to="/profile" className="shrink-0 text-sm font-medium text-accent hover:underline">View profile</Link>
      </div>
      <form noValidate onSubmit={submit} className="space-y-4" aria-label="Profile">
        <div className="space-y-1.5">
          <label htmlFor={`${id}-name`} className="text-sm font-medium">Display name</label>
          <input
            id={`${id}-name`}
            value={form.display_name}
            onChange={(e) => set("display_name", e.target.value)}
            maxLength={MAX_DISPLAY_NAME}
            autoComplete="name"
            placeholder="How your name appears"
            className={inputClass}
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor={`${id}-username`} className="text-sm font-medium">Username</label>
          <div className="flex items-center rounded-lg border border-border bg-bg focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/40">
            <span className="pl-3 text-ink-muted" aria-hidden>@</span>
            <input
              id={`${id}-username`}
              value={form.username}
              onChange={(e) => set("username", e.target.value)}
              maxLength={21}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              aria-describedby={`${id}-username-status`}
              aria-invalid={blocked && changes.username !== undefined}
              placeholder={p.username ? undefined : "choose_one"}
              className="w-full rounded-lg bg-transparent py-2 pl-1 pr-3 text-ink placeholder:text-ink-muted focus:outline-none"
            />
          </div>
          {p.username !== null && !form.username.trim() ? (
            <p id={`${id}-username-status`} className="text-xs text-bad">You can change your username, but not remove it.</p>
          ) : (
            <p id={`${id}-username-status`} aria-live="polite" className={`text-xs ${username.tone}`}>{username.text}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between">
            <label htmlFor={`${id}-bio`} className="text-sm font-medium">Bio</label>
            <span className="text-xs tabular text-ink-muted" aria-hidden>{form.bio.length}/{MAX_BIO}</span>
          </div>
          <textarea
            id={`${id}-bio`}
            value={form.bio}
            onChange={(e) => set("bio", e.target.value)}
            maxLength={MAX_BIO}
            rows={3}
            placeholder="A line or two about your game: how long you've played, what you're working on…"
            className={inputClass}
          />
        </div>
        {save.error && <ErrorText>{settingsErrorMessage(save.error)}</ErrorText>}
        {saved && <p role="status" className="text-sm text-good">Profile saved.</p>}
        <button
          type="submit"
          disabled={blocked || Object.keys(changes).length === 0 || save.isPending}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save profile"}
        </button>
      </form>
    </section>
  );
}

function FriendRequestsSetting() {
  const id = useId();
  const profile = useProfile();
  const save = useUpdateProfile();
  const on = profile.data?.accept_requests ?? true;
  return (
    <div className="space-y-1">
      <label className="flex cursor-pointer items-start gap-3 text-sm">
        <input
          type="checkbox"
          checked={on}
          disabled={!profile.data || save.isPending}
          onChange={(e) => save.mutate({ accept_requests: e.target.checked })}
          aria-describedby={`${id}-hint`}
          className="mt-0.5 size-4 accent-[var(--accent)]"
        />
        <span>
          <span className="font-medium">Let people send me friend requests</span>
          <span id={`${id}-hint`} className="block text-ink-muted">
            {on ? "Anyone who knows your username can ask." : "Nobody can send you one. You can still send requests yourself."}
          </span>
        </span>
      </label>
      {save.error && <ErrorText>{settingsErrorMessage(save.error)}</ErrorText>}
    </div>
  );
}

function BlockedPeople() {
  const blocks = useBlocks();
  const unblock = useUnblock();
  const items = blocks.data ?? [];
  return (
    <div id="blocked" className="scroll-mt-20 space-y-2">
      <h3 className="text-sm font-semibold">Blocked people</h3>
      {blocks.isError ? (
        <ErrorText>{settingsErrorMessage(blocks.error)}</ErrorText>
      ) : items.length === 0 ? (
        <p className="text-sm text-ink-muted">You haven't blocked anyone.</p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {items.map((b) => (
            <li key={b.person.username ?? b.blocked_at} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <span className="min-w-0 truncate">
                {b.person.display_name ?? `@${b.person.username}`}
                {b.person.display_name && <span className="text-ink-muted"> @{b.person.username}</span>}
              </span>
              <button
                type="button"
                disabled={unblock.isPending || !b.person.username}
                onClick={() => unblock.mutate(b.person.username!)}
                className="shrink-0 font-medium text-accent hover:underline disabled:opacity-50"
                aria-label={`Unblock ${b.person.display_name ?? b.person.username}`}
              >
                Unblock
              </button>
            </li>
          ))}
        </ul>
      )}
      {unblock.error && <ErrorText>{settingsErrorMessage(unblock.error)}</ErrorText>}
    </div>
  );
}

function FriendsSettings() {
  const id = useId();
  return (
    <section aria-labelledby={`${id}-title`} className="space-y-4 rounded-xl border border-border bg-surface p-5">
      <h2 id={`${id}-title`} className="font-semibold">Friends and privacy</h2>
      <FriendRequestsSetting />
      <BlockedPeople />
    </section>
  );
}

function ChangePassword() {
  const id = useId();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!current) return setProblem("Enter your current password.");
    if (next.length < MIN_PASSWORD_LENGTH) return setProblem(`Use at least ${MIN_PASSWORD_LENGTH} characters for the new password.`);
    if (next === current) return setProblem("That's your current password. Choose a different one.");
    setProblem(null);
    change.mutate({ current, next }, {
      onSuccess: () => {
        setCurrent("");
        setNext("");
      },
    });
  }

  return (
    <section aria-labelledby={`${id}-title`} className="space-y-3 rounded-xl border border-border bg-surface p-5">
      <h2 id={`${id}-title`} className="font-semibold">Password</h2>
      <form noValidate onSubmit={submit} className="space-y-4" aria-label="Change your password">
        <PasswordInput id={`${id}-current`} label="Current password" value={current} onChange={(v) => { setCurrent(v); change.reset(); }} autoComplete="current-password" />
        <PasswordInput id={`${id}-new`} label="New password" value={next} onChange={(v) => { setNext(v); change.reset(); }} autoComplete="new-password" />
        <p className="text-xs text-ink-muted">At least {MIN_PASSWORD_LENGTH} characters. A few unrelated words make a strong one.</p>
        {(problem || change.error) && <ErrorText>{problem ?? settingsErrorMessage(change.error)}</ErrorText>}
        {change.isSuccess && (
          <p role="status" className="text-sm text-good">Password changed. Every other device has been signed out.</p>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <button type="submit" disabled={change.isPending} className={secondaryButton}>
            {change.isPending ? "Changing…" : "Change password"}
          </button>
          <Link to="/forgot-password" className="text-sm text-ink-muted underline hover:text-ink">Forgot your current password?</Link>
        </div>
      </form>
    </section>
  );
}

export function SettingsPage() {
  const session = useSession();
  const user = session.data;
  if (!user) return null;
  return (
    <div className="mx-auto w-full max-w-xl space-y-6 py-4">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <VerifyEmailBanner />
      <ProfileSettings />
      <FriendsSettings />
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
        <div className="pt-2 text-sm">
          <ChangeEmail current={user.email} />
        </div>
      </section>
      <ChangePassword />
      <DownloadData />
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
