import { Link } from "react-router";

import type { SharedServe } from "../../api/types";
import { bandOf } from "../../lib/score";
import { SCORE_TEXT } from "../results/MetricCards";

/** A serve sent in a message: opens the analysis, or says it isn't available any more. */
export function ServeCard({ serve, mine }: { serve: SharedServe; mine: boolean }) {
  if (!serve.available || !serve.analysis_id) {
    return (
      <p className="rounded-xl border border-dashed border-border px-3 py-2 text-sm italic text-ink-muted">
        This serve isn't available any more.
      </p>
    );
  }
  const when = serve.recorded_at ? new Date(serve.recorded_at).toLocaleDateString(undefined, { dateStyle: "medium" }) : "";
  const score = serve.overall_score;
  return (
    <Link
      to={`/analyses/${serve.analysis_id}`}
      className="flex w-64 max-w-full items-center gap-3 overflow-hidden rounded-xl border border-border bg-surface p-2 text-ink hover:bg-surface-2"
      aria-label={`Open ${mine ? "your" : "their"} serve from ${when}${score != null ? `, scored ${score}` : ""}`}
    >
      {serve.thumbnail_url ? (
        <img src={serve.thumbnail_url} alt="" className="aspect-video w-24 shrink-0 rounded-lg bg-black object-contain" />
      ) : (
        <span className="aspect-video w-24 shrink-0 rounded-lg bg-surface-2" aria-hidden />
      )}
      <span className="min-w-0 space-y-0.5">
        <span className="block text-sm font-medium">{mine ? "Your serve" : "A serve"}</span>
        <span className="block text-xs text-ink-muted">{when}</span>
        {score != null && <span className={`tabular block text-lg font-semibold ${SCORE_TEXT[bandOf(score)]}`}>{score}</span>}
      </span>
    </Link>
  );
}
