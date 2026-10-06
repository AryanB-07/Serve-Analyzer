import { useState } from "react";

import { useDeleteAnalysis } from "../api/queries";

/** Delete with an inline "are you sure" step. ``onDeleted`` runs once the server confirms. */
export function DeleteAnalysisButton({
  id,
  filename,
  onDeleted,
  className = "",
}: {
  id: string;
  filename: string;
  onDeleted?: () => void;
  className?: string;
}) {
  const [confirming, setConfirming] = useState(false);
  const remove = useDeleteAnalysis(onDeleted);

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        aria-label={`Delete ${filename}`}
        className={`rounded-md px-2 py-1 text-sm text-ink-muted hover:text-bad ${className}`}
      >
        Delete
      </button>
    );
  }
  return (
    <div role="group" aria-label={`Delete ${filename}?`} className={`flex flex-wrap items-center gap-2 text-sm ${className}`}>
      <span>Delete the video and results?</span>
      <button
        type="button"
        onClick={() => remove.mutate(id)}
        disabled={remove.isPending}
        className="rounded-md bg-bad px-2.5 py-1 font-semibold text-on-accent disabled:opacity-50"
      >
        {remove.isPending ? "Deleting…" : "Delete"}
      </button>
      <button
        type="button"
        onClick={() => {
          setConfirming(false);
          remove.reset();
        }}
        className="rounded-md px-2 py-1 text-ink-muted hover:text-ink"
      >
        Cancel
      </button>
      {remove.error && (
        <span role="alert" className="w-full text-bad">
          Couldn't delete it: {remove.error.message}
        </span>
      )}
    </div>
  );
}
