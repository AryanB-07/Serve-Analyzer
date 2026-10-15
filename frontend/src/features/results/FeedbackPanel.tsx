import type { AnalysisResult, FeedbackItem } from "../../api/types";
import { StatusIcon } from "../../components/StatusIcon";
import { PHASE_LABELS } from "../../lib/phases";
import type { ResultsMode } from "../../lib/useResultsMode";
import { usePlayheadStore } from "../../playhead/context";

function FeedbackBody({ item, mode }: { item: FeedbackItem; mode: ResultsMode }) {
  // Simple mode uses the version without numbers (older results don't have one).
  const text = mode === "simple" ? (item.plain ?? item.text) : item.text;
  return (
    <>
      <StatusIcon status={item.status ?? "unknown"} className="mt-1 size-3.5" />
      <span className="text-sm leading-relaxed">{text}</span>
    </>
  );
}

/** Coaching points, each a link to the moment in the video it is about. */
export function FeedbackPanel({ result, mode = "advanced" }: { result: AnalysisResult; mode?: ResultsMode }) {
  const store = usePlayheadStore();
  return (
    <section aria-labelledby="feedback-heading" className="rounded-xl border border-border bg-surface p-4">
      <h2 id="feedback-heading" className="mb-3 text-lg font-semibold">
        Coaching feedback
      </h2>
      <ol className="space-y-2">
        {result.feedback.map((item, index) => {
          const frame = item.phase ? result.phases[item.phase] : null;
          if (item.phase && frame !== null) {
            const label = PHASE_LABELS[item.phase];
            return (
              <li key={index}>
                <button
                  type="button"
                  onClick={() => store.seek(frame)}
                  className="group grid w-full grid-cols-[auto_1fr] gap-x-2.5 gap-y-1 rounded-lg p-2 text-left hover:bg-surface-2"
                >
                  <FeedbackBody item={item} mode={mode} />
                  <span className="col-start-2 text-xs font-medium text-accent group-hover:underline">
                    Watch {label.toLowerCase()} · {(frame / store.fps).toFixed(2)}s
                  </span>
                </button>
              </li>
            );
          }
          return (
            <li key={index} className="grid grid-cols-[auto_1fr] gap-x-2.5 p-2">
              <FeedbackBody item={item} mode={mode} />
            </li>
          );
        })}
      </ol>
    </section>
  );
}
