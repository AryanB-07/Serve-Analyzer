import { useId } from "react";

import { useAnalysesList } from "../../api/queries";
import type { AnalysisSummary } from "../../api/types";
import { bandOf } from "../../lib/score";
import { SCORE_TEXT } from "../results/MetricCards";

/** Choose one of your finished serves (newest first): for sending, or comparing. */
export function ServePicker({ title, onPick, onCancel, exclude }: {
  title: string;
  onPick: (analysis: AnalysisSummary) => void;
  onCancel: () => void;
  exclude?: string;
}) {
  const id = useId();
  const list = useAnalysesList();
  const items = (list.data?.pages.flatMap((p) => p.items) ?? []).filter((a) => a.status === "succeeded" && a.id !== exclude);
  return (
    <div role="group" aria-labelledby={id} className="space-y-2 rounded-xl border border-border bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <p id={id} className="text-sm font-semibold">{title}</p>
        <button type="button" onClick={onCancel} className="text-sm text-ink-muted hover:text-ink">Cancel</button>
      </div>
      {list.isPending ? (
        <p className="text-sm text-ink-muted">Loading your serves…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-ink-muted">You don't have a finished serve yet.</p>
      ) : (
        <ul className="max-h-64 space-y-1 overflow-y-auto">
          {items.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => onPick(a)}
                className="flex w-full items-center gap-3 rounded-lg p-1.5 text-left hover:bg-surface-2"
              >
                {a.thumbnail_url ? (
                  <img src={a.thumbnail_url} alt="" className="aspect-video w-16 shrink-0 rounded bg-black object-contain" />
                ) : (
                  <span className="aspect-video w-16 shrink-0 rounded bg-surface-2" aria-hidden />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{a.filename}</span>
                  <span className="block text-xs text-ink-muted">
                    {new Date(a.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                  </span>
                </span>
                {a.overall_score != null && (
                  <span className={`tabular text-sm font-semibold ${SCORE_TEXT[bandOf(a.overall_score)]}`}>{a.overall_score}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      {list.hasNextPage && (
        <button type="button" onClick={() => list.fetchNextPage()} className="text-sm text-accent hover:underline">Show older serves</button>
      )}
    </div>
  );
}
