import { useId, useState, type FormEvent } from "react";

import { useBlock } from "../../api/friends";
import { useReport } from "../../api/messages";
import type { UserReportReason } from "../../api/types";
import { friendsErrorMessage } from "../friends/FriendsPage";

const REASONS: { value: UserReportReason; label: string }[] = [
  { value: "harassment", label: "Harassment or bullying" },
  { value: "spam", label: "Spam" },
  { value: "inappropriate", label: "Something inappropriate" },
  { value: "impersonation", label: "Pretending to be someone else" },
  { value: "other", label: "Something else" },
];

/** Report a person, or one of their messages, with the option of blocking them too. */
export function ReportForm({ username, name, messageId, postId, commentId, onDone, onBlocked }: {
  username: string;
  name: string;
  messageId?: string;
  postId?: string;
  commentId?: string;
  onDone: () => void;
  onBlocked?: () => void;
}) {
  const id = useId();
  const report = useReport();
  const block = useBlock();
  const [reason, setReason] = useState<UserReportReason | null>(null);
  const [note, setNote] = useState("");
  const [alsoBlock, setAlsoBlock] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason) return;
    try {
      await report.mutateAsync({ username, message_id: messageId ?? null, post_id: postId ?? null, comment_id: commentId ?? null,
        reason, note: note.trim() || null });
      if (alsoBlock) {
        await block.mutateAsync(username);
        onBlocked?.();
      }
      setSent(true);
    } catch {
      // shown below
    }
  }

  if (sent) {
    return (
      <div role="status" className="space-y-2 rounded-xl border border-border bg-surface p-4 text-sm">
        <p>Thanks. We'll look at it{alsoBlock ? `, and you've blocked ${name}` : ""}.</p>
        <button type="button" onClick={onDone} className="font-medium text-accent hover:underline">Close</button>
      </div>
    );
  }
  const error = report.error ?? block.error;
  return (
    <form onSubmit={submit} aria-labelledby={`${id}-title`} className="space-y-3 rounded-xl border border-bad/40 bg-surface p-4">
      <p id={`${id}-title`} className="font-medium">
        {messageId ? `Report this message from ${name}` : postId ? `Report ${name}'s post` : commentId ? `Report ${name}'s comment` : `Report ${name}`}
      </p>
      <fieldset className="space-y-1.5">
        <legend className="sr-only">Reason</legend>
        {REASONS.map((r) => (
          <label key={r.value} className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="radio" name={`${id}-reason`} checked={reason === r.value} onChange={() => setReason(r.value)} className="accent-[var(--accent)]" />
            {r.label}
          </label>
        ))}
      </fieldset>
      <label className="block space-y-1 text-sm">
        <span>Anything to add? <span className="text-ink-muted">(optional)</span></span>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} rows={2}
          className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40" />
      </label>
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input type="checkbox" checked={alsoBlock} onChange={(e) => setAlsoBlock(e.target.checked)} className="size-4 accent-[var(--accent)]" />
        Also block {name}
      </label>
      {error && <p role="alert" className="text-sm text-bad">{friendsErrorMessage(error)}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={!reason || report.isPending || block.isPending}
          className="rounded-lg bg-bad px-4 py-2 text-sm font-semibold text-on-accent disabled:opacity-50">
          {report.isPending || block.isPending ? "Sending…" : "Send report"}
        </button>
        <button type="button" onClick={onDone} className="px-3 text-sm text-ink-muted hover:text-ink">Cancel</button>
      </div>
      <p className="text-xs text-ink-muted">They won't be told who reported them. A copy of what they wrote is kept with the report.</p>
    </form>
  );
}
