import { useEffect, useMemo, useRef, type KeyboardEvent, type PointerEvent } from "react";

import type { PhaseFrames, PhaseName } from "../../api/types";
import { PHASE_LABELS, SEGMENT_LABELS, segmentAt, type Segment } from "../../lib/phases";
import { fractionForFrame, frameAtFraction, phaseMarkers, timelineSegments } from "../../lib/timeline";
import { usePlayheadStore } from "../../playhead/context";

const ALL_PHASES: PhaseName[] = ["trophy", "racket_drop", "contact"];

function segmentStyle(segment: Segment) {
  return { background: `var(--phase-${segment})` };
}

function formatTime(frame: number, fps: number) {
  return `${(frame / fps).toFixed(2)}s`;
}

export function PhaseTimeline({ phases }: { phases: PhaseFrames }) {
  const store = usePlayheadStore();
  const { nFrames, fps } = store;
  const segments = useMemo(() => timelineSegments(phases, nFrames), [phases, nFrames]);
  const markers = useMemo(() => phaseMarkers(phases), [phases]);
  const trackRef = useRef<HTMLDivElement>(null);
  const playheadRef = useRef<HTMLDivElement>(null);
  const scrubbing = useRef(false);

  // Playhead position and slider value follow the store without re-rendering.
  useEffect(() => {
    const update = () => {
      const { frame } = store.getState();
      if (playheadRef.current) {
        playheadRef.current.style.left = `${fractionForFrame(frame, nFrames) * 100}%`;
      }
      const track = trackRef.current;
      if (track) {
        track.setAttribute("aria-valuenow", String(frame + 1));
        track.setAttribute(
          "aria-valuetext",
          `Frame ${frame + 1} of ${nFrames}, ${formatTime(frame, fps)}, ${SEGMENT_LABELS[segmentAt(frame, phases)]}`,
        );
      }
    };
    update();
    return store.subscribe(update);
  }, [store, nFrames, fps, phases]);

  function seekToPointer(e: PointerEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    store.seek(frameAtFraction((e.clientX - rect.left) / rect.width, nFrames));
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const jump = Math.max(1, Math.round(fps));
    const frame = store.getState().frame;
    const target =
      e.key === "PageUp" ? frame + jump : e.key === "PageDown" ? frame - jump : null;
    if (target === null) return;
    e.preventDefault();
    store.seek(target);
  }

  return (
    <div className="space-y-2">
      <div className="relative pt-3">
        <div
          ref={trackRef}
          role="slider"
          tabIndex={0}
          aria-label="Timeline"
          aria-valuemin={1}
          aria-valuemax={nFrames}
          aria-valuenow={1}
          onKeyDown={onKeyDown}
          onPointerDown={(e) => {
            scrubbing.current = true;
            e.currentTarget.setPointerCapture?.(e.pointerId);
            seekToPointer(e);
          }}
          onPointerMove={(e) => scrubbing.current && seekToPointer(e)}
          onPointerUp={() => (scrubbing.current = false)}
          onPointerCancel={() => (scrubbing.current = false)}
          className="relative flex h-9 cursor-pointer touch-none select-none overflow-hidden rounded-lg"
          data-testid="timeline-track"
        >
          {segments.map((s) => (
            <div
              key={s.segment}
              style={{ ...segmentStyle(s.segment), width: `${((s.end - s.start) / nFrames) * 100}%` }}
              className={`flex h-full min-w-0 items-center border-r-2 border-bg px-2 text-xs font-semibold last:border-r-0 ${
                s.segment === "stance" ? "text-ink" : "text-white"
              }`}
            >
              <span className="truncate">{SEGMENT_LABELS[s.segment]}</span>
            </div>
          ))}
        </div>

        {markers.map(({ phase, frame }) => (
          <button
            key={phase}
            type="button"
            onClick={() => store.seek(frame)}
            aria-label={`Jump to ${PHASE_LABELS[phase].toLowerCase()} (${formatTime(frame, fps)})`}
            title={`${PHASE_LABELS[phase]} · ${formatTime(frame, fps)}`}
            style={{ left: `${fractionForFrame(frame, nFrames) * 100}%` }}
            className="group absolute top-0 z-10 flex h-12 w-6 -translate-x-1/2 flex-col items-center"
            data-testid={`marker-${phase}`}
          >
            <svg viewBox="0 0 12 10" className="size-3 drop-shadow" aria-hidden>
              <path d="M0 0h12L6 10Z" style={{ fill: `var(--phase-${phase})` }} stroke="var(--bg)" strokeWidth="1.2" />
            </svg>
            <span className="h-9 w-0.5 bg-white/80 group-hover:bg-white" />
          </button>
        ))}

        <div
          ref={playheadRef}
          className="pointer-events-none absolute top-1.5 bottom-[-6px] z-20 w-0.5 -translate-x-1/2 rounded-full bg-ink shadow-[0_0_0_1px_var(--bg)]"
          aria-hidden
        >
          <span className="absolute -top-1 left-1/2 size-2.5 -translate-x-1/2 rounded-full bg-ink ring-2 ring-bg" />
        </div>
      </div>

      <div className="flex flex-wrap gap-2" aria-label="Jump to phase">
        <button
          type="button"
          onClick={() => store.seek(0)}
          className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-sm hover:border-accent"
        >
          <span className="size-2.5 rounded-full" style={segmentStyle("stance")} aria-hidden />
          Stance <span className="tabular text-ink-muted">0.00s</span>
        </button>
        {ALL_PHASES.map((phase) => {
          const frame = phases[phase];
          if (frame === null) {
            return (
              <span
                key={phase}
                className="inline-flex items-center gap-2 rounded-full border border-dashed border-border px-3 py-1 text-sm text-ink-muted"
              >
                <span className="size-2.5 rounded-full opacity-40" style={segmentStyle(phase)} aria-hidden />
                {PHASE_LABELS[phase]} <span className="text-xs">not detected</span>
              </span>
            );
          }
          return (
            <button
              key={phase}
              type="button"
              onClick={() => store.seek(frame)}
              className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-sm hover:border-accent"
            >
              <span className="size-2.5 rounded-full" style={segmentStyle(phase)} aria-hidden />
              {PHASE_LABELS[phase]} <span className="tabular text-ink-muted">{formatTime(frame, fps)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
