import type { PhaseFrames } from "../../api/types";
import { StatusIcon, STATUS_TEXT } from "../../components/StatusIcon";
import { SEGMENT_LABELS, segmentAt } from "../../lib/phases";
import { usePlayhead, usePlayheadStore } from "../../playhead/context";

/** Re-renders once per frame, but it is a few text nodes. */
export function FrameCounter() {
  const { nFrames, fps } = usePlayheadStore();
  const frame = usePlayhead((s) => s.frame);
  return (
    <span className="tabular text-sm text-ink-muted" data-testid="frame-counter">
      Frame <span className="text-ink">{frame + 1}</span> / {nFrames} ·{" "}
      <span className="text-ink">{(frame / fps).toFixed(2)}s</span>
    </span>
  );
}

/** Re-renders only when the segment changes (a handful of times per clip). */
export function CurrentPhase({ phases }: { phases: PhaseFrames }) {
  const segment = usePlayhead((s) => segmentAt(s.frame, phases));
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full bg-surface-2 px-2.5 py-0.5 text-sm font-medium"
      aria-live="polite"
      data-testid="current-phase"
    >
      <span className="size-2 rounded-full" style={{ background: `var(--phase-${segment})` }} aria-hidden />
      {SEGMENT_LABELS[segment]}
    </span>
  );
}

export function StatusKey() {
  return (
    <ul className="flex items-center gap-3 text-sm text-ink-muted" aria-label="Joint marker key">
      {(["good", "borderline", "off"] as const).map((status) => (
        <li key={status} className="flex items-center gap-1.5">
          <StatusIcon status={status} className="size-3" />
          {STATUS_TEXT[status]}
        </li>
      ))}
    </ul>
  );
}
