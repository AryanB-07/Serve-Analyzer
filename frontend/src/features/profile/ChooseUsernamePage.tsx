import { useId, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { ApiError } from "../../api/client";
import { useUpdateProfile } from "../../api/profile";
import { UsernameField, useUsernameStatus } from "../../components/UsernameField";
import { safeNext } from "../../lib/safeNext";
import { authErrorMessage } from "../auth/AuthForm";

/** For accounts made before a username was required at signup: choose one, then carry on. */
export function ChooseUsernamePage() {
  const id = useId();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const save = useUpdateProfile();
  const [value, setValue] = useState("");
  const status = useUsernameStatus(value, null);
  const [problem, setProblem] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!status.usable) return setProblem(status.name ? "Choose a username that's available." : "Choose a username.");
    setProblem(null);
    save.mutate({ username: status.name }, { onSuccess: () => navigate(safeNext(params.get("next")), { replace: true }) });
  }

  const error = problem ?? (save.error instanceof ApiError && save.error.status < 500 ? save.error.message
    : save.error ? authErrorMessage(save.error) : null);
  return (
    <div className="mx-auto w-full max-w-sm py-8">
      <h1 className="text-3xl font-semibold tracking-tight">Choose a username</h1>
      <p className="mt-2 text-ink-muted">
        Every account has one now. It's how friends find and follow you. You can change it later in Settings.
      </p>
      <form noValidate onSubmit={submit} aria-label="Choose a username" className="mt-6 space-y-4 rounded-xl border border-border bg-surface p-5">
        <UsernameField id={`${id}-username`} value={value} onChange={(v) => { setValue(v); save.reset(); }} status={status} />
        {error && <p role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}
        <button type="submit" disabled={save.isPending}
          className="w-full rounded-lg bg-accent px-5 py-2.5 font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50">
          {save.isPending ? "Saving…" : "Continue"}
        </button>
      </form>
    </div>
  );
}
