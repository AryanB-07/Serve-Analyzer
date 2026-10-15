import { useEffect, useState, type ReactNode } from "react";

import { useUsernameCheck } from "../api/profile";
import { normaliseUsername, usernameProblem } from "../lib/username";

const HINT = "Letters, numbers and underscores, 3 to 20 of them. People who know it can find and follow you.";

/**
 * The username as it's typed, checked against the rules here, then (after a pause) with the API.
 * ``current`` is the username it may keep (yours, in Settings); ``signedOut`` uses the signup
 * form's check, which needs no account.
 */
export function useUsernameStatus(value: string, current: string | null, signedOut = false) {
  const name = normaliseUsername(value);
  const [settled, setSettled] = useState(name);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(name), 400);
    return () => clearTimeout(timer);
  }, [name]);
  const local = name ? usernameProblem(name) : null;
  const ask = !name || local || name === current || settled !== name ? null : name;
  const check = useUsernameCheck(ask, signedOut);
  const answer = check.data && check.data.username === name ? check.data : null;
  let text: ReactNode = HINT;
  let tone = "text-ink-muted";
  if (local) [text, tone] = [local, "text-bad"];
  else if (name && name === current) text = "This is your username.";
  else if (answer) [text, tone] = answer.available ? [`@${name} is available.`, "text-good"] : [answer.problem, "text-bad"];
  else if (name) text = "Checking…";
  // Saving waits for the API's answer, and is refused when the name isn't available.
  const usable = (name !== "" && name === current) || (!local && answer?.available === true);
  return { name, text, tone, usable };
}

/** An @-prefixed username input with its live status underneath. */
export function UsernameField({ id, value, onChange, status, label = "Username", placeholder }: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  status: ReturnType<typeof useUsernameStatus>;
  label?: string;
  placeholder?: string;
}) {
  const invalid = value.trim() !== "" && !status.usable && status.tone === "text-bad";
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <div className="flex items-center rounded-lg border border-border bg-bg focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/40">
        <span className="pl-3 text-ink-muted" aria-hidden>@</span>
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          maxLength={21}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          aria-describedby={`${id}-status`}
          aria-invalid={invalid}
          placeholder={placeholder}
          className="w-full rounded-lg bg-transparent py-2 pl-1 pr-3 text-ink placeholder:text-ink-muted focus:outline-none"
        />
      </div>
      <p id={`${id}-status`} aria-live="polite" className={`text-xs ${status.tone}`}>{status.text}</p>
    </div>
  );
}
