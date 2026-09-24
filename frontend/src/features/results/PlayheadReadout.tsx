import type { PhaseFrames } from "../../api/types";
import { StatusIcon, STATUS_TEXT } from "../../components/StatusIcon";
import { SEGMENT_LABELS, segmentAt } from "../../lib/phases";
import { usePlayhead } from "../../playhead/context";

/** Re-renders once per frame, but it is two text nodes. */
function FrameCounter({ nFrames, fps }: { nFrames: number; fps: number }) {
  const frame = usePlayhead((s) => s.frame);
  return (
    <span className="tabular text-ink-muted">
      Frame <span className="text-ink">{frame + 1}</span> / {nFrames} ·{" "}
      <span className="text-ink">{(frame / fps).toFixed(2)}s</span>
    </span>
  );
}

/** Re-renders only when the segment changes (a handful of times per clip). */
function CurrentPhase({ phases }: { phases: PhaseFrames }) {
  const segment = usePlayhead((s) => segmentAt(s.frame, phases));
  return (
    <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-sm font-medium" aria-live="polite">
      {SEGMENT_LABELS[segment]}
    </span>
  );
}

export function PlayheadReadout({ phases, nFrames, fps }: { phases: PhaseFrames; nFrames: number; fps: number }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      <CurrentPhase phases={phases} />
      <FrameCounter nFrames={nFrames} fps={fps} />
      <ul className="ml-auto flex items-center gap-3 text-ink-muted" aria-label="Joint colour key">
        {(["good", "borderline", "off"] as const).map((status) => (
          <li key={status} className="flex items-center gap-1.5">
            <StatusIcon status={status} className="size-3" />
            {STATUS_TEXT[status]}
          </li>
        ))}
      </ul>
    </div>
  );
}
