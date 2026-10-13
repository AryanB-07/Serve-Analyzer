import { useId, useState, type FormEvent } from "react";

import { useReport, useReportAnalysis } from "../../api/queries";
import type { ReportReason } from "../../api/types";
import { authErrorMessage } from "../auth/AuthForm";

export const REASON_LABELS: Record<ReportReason, string> = {
  not_a_serve: "This isn't a serve",
  wrong_phases: "A phase is marked at the wrong moment",
  wrong_tracking: "The skeleton doesn't follow my body",
  wrong_feedback: "The angles or feedback look wrong",
  was_a_serve: "This was a serve",
  other: "Something else",
};

/** Which reasons fit how the analysis ended (the API refuses the others). */
export const REASONS: Record<"succeeded" | "failed", ReportReason[]> = {
  succeeded: ["not_a_serve", "wrong_phases", "wrong_tracking", "wrong_feedback", "other"],
  failed: ["was_a_serve", "other"],
};

export const MAX_NOTE_LENGTH = 1000;

/**
 * "This result looks wrong": a reason and an optional note, stored with the analysis.
 * The reports are how the pipeline's mistakes get found (python -m serve_api.reports lists them).
 */
export function ReportProblem({ analysisId, outcome, prompt }: {
  analysisId: string;
  outcome: "succeeded" | "failed";
  /** The button's text while no report has been sent. */
  prompt?: string;
}) {
  const id = useId();
  const existing = useReport(analysisId);
  const send = useReportAnalysis(analysisId);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [note, setNote] = useState("");
  const reasons = REASONS[outcome];
  const sent = existing.data;

  function start() {
    setReason(sent && reasons.includes(sent.reason) ? sent.reason : outcome === "failed" ? "was_a_serve" : null);
    setNote(sent?.note ?? "");
    send.reset();
    setOpen(true);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason) return;
    send.mutate({ reason, note: note.trim() || null }, { onSuccess: () => setOpen(false) });
  }

  if (!open) {
    return (
      <div className="space-y-1 text-sm">
        {sent ? (
          <p role="status" className="text-ink-muted">
            Thanks, we've noted that: <span className="text-ink">{REASON_LABELS[sent.reason].toLowerCase()}</span>.{" "}
            <button type="button" onClick={start} className="font-medium text-accent underline">Change</button>
          </p>
        ) : (
          <button type="button" onClick={start} className="font-medium text-accent hover:underline">
            {prompt ?? "This result looks wrong?"}
          </button>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={submit} aria-labelledby={`${id}-title`} className="space-y-3 rounded-xl border border-border bg-surface p-4 text-left">
      <h2 id={`${id}-title`} className="font-semibold">What looks wrong?</h2>
      <fieldset className="space-y-1.5">
        <legend className="sr-only">Reason</legend>
        {reasons.map((r) => (
          <label key={r} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name={`${id}-reason`}
              value={r}
              checked={reason === r}
              onChange={() => setReason(r)}
              className="accent-accent"
            />
            {REASON_LABELS[r]}
          </label>
        ))}
      </fieldset>
      <div className="space-y-1.5">
        <label htmlFor={`${id}-note`} className="text-sm font-medium">
          Anything to add? <span className="font-normal text-ink-muted">(optional)</span>
        </label>
        <textarea
          id={`${id}-note`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={MAX_NOTE_LENGTH}
          rows={3}
          placeholder={outcome === "failed" ? "For example: a kick serve, filmed from behind" : "For example: contact is a few frames early"}
          className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
      </div>
      <p className="text-xs text-ink-muted">
        Your answer is saved with this analysis to help us improve it, and deleted when you delete the analysis.
      </p>
      {send.error && <p role="alert" className="text-sm text-bad">{authErrorMessage(send.error)}</p>}
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={!reason || send.isPending}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
        >
          {send.isPending ? "Sending…" : "Send"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-lg px-4 py-2 text-sm text-ink-muted hover:text-ink">
          Cancel
        </button>
      </div>
    </form>
  );
}
