import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import type { AnalysisResult, FramesPayload } from "../../../api/types";
import {
  chartColumns,
  formatMetric,
  phasePoints,
  referenceBands,
  seriesSummary,
  yRange,
  type Band,
  type ChartSpec,
  type PhasePoint,
} from "../../../lib/chartData";
import { timelineSegments, type TimelineSegment } from "../../../lib/timeline";
import { cssVar, useTheme, withAlpha } from "../../../lib/useTheme";
import { usePlayheadStore } from "../../../playhead/context";
import { drawStatusMarker } from "../overlay/drawOverlay";

const HEIGHT = 150;
const FONT = "11px ui-sans-serif, system-ui, sans-serif";

interface ChartColors {
  ink: string;
  muted: string;
  grid: string;
  good: string;
  phase: Record<string, string>;
}

function readColors(): ChartColors {
  return {
    ink: cssVar("--ink"),
    muted: cssVar("--ink-muted"),
    grid: withAlpha(cssVar("--border"), 0.7),
    good: cssVar("--good"),
    phase: {
      trophy: cssVar("--phase-trophy"),
      racket_drop: cssVar("--phase-racket_drop"),
      contact: cssVar("--phase-contact"),
    },
  };
}

/** Horizontal canvas-pixel span of a frame range, clipped to the plot area. */
function frameSpan(u: uPlot, start: number, end: number, fps: number): [number, number] {
  const left = u.bbox.left;
  const right = u.bbox.left + u.bbox.width;
  const x0 = Math.max(left, u.valToPos(start / fps, "x", true));
  const x1 = Math.min(right, u.valToPos(end / fps, "x", true));
  return [x0, x1];
}

function drawPhaseShading(u: uPlot, segments: TimelineSegment[], fps: number, colors: ChartColors) {
  const { ctx, bbox } = u;
  for (const s of segments) {
    if (s.segment === "stance") continue;
    const [x0, x1] = frameSpan(u, s.start, s.end, fps);
    ctx.fillStyle = withAlpha(colors.phase[s.segment]!, 0.12);
    ctx.fillRect(x0, bbox.top, x1 - x0, bbox.height);
  }
}

function drawBands(u: uPlot, bands: Band[], fps: number, colors: ChartColors) {
  const { ctx } = u;
  for (const b of bands) {
    const [x0, x1] = frameSpan(u, b.startFrame, b.endFrame, fps);
    const yTop = u.valToPos(b.hi, "y", true);
    const yBottom = u.valToPos(b.lo, "y", true);
    ctx.fillStyle = withAlpha(colors.good, 0.16);
    ctx.fillRect(x0, yTop, x1 - x0, yBottom - yTop);
    ctx.save();
    ctx.strokeStyle = withAlpha(colors.good, 0.7);
    ctx.lineWidth = uPlot.pxRatio;
    ctx.setLineDash([4 * uPlot.pxRatio, 3 * uPlot.pxRatio]);
    ctx.beginPath();
    for (const y of [yTop, yBottom]) {
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
    }
    ctx.stroke();
    ctx.restore();
  }
}

function drawPhasePoints(u: uPlot, points: PhasePoint[], fps: number) {
  for (const p of points) {
    const x = u.valToPos(p.frame / fps, "x", true);
    const y = u.valToPos(p.value, "y", true);
    drawStatusMarker(u.ctx, p.status, x, y, 5 * uPlot.pxRatio);
  }
}

/**
 * One metric over time. uPlot draws the static chart once; the playhead line
 * and value readout are moved from a store subscription, so playback never
 * redraws the canvas or re-renders React.
 *
 * Hover (while paused) previews: the video follows the pointer and returns
 * when the pointer leaves. Clicking or tapping commits the seek.
 */
export function AngleChart({
  spec,
  frames,
  result,
}: {
  spec: ChartSpec;
  frames: FramesPayload;
  result: AnalysisResult;
}) {
  const store = usePlayheadStore();
  const theme = useTheme();
  const plotRef = useRef<HTMLDivElement>(null);
  const readoutRefs = useRef<(HTMLSpanElement | null)[]>([]);

  const columns = useMemo(() => chartColumns(frames, spec), [frames, spec]);
  const bands = useMemo(
    () => referenceBands(spec, result.ranges, result.phases, frames.n_frames),
    [spec, result, frames.n_frames],
  );
  const points = useMemo(() => phasePoints(spec, result), [spec, result]);
  const hasData = useMemo(() => columns.slice(1).some((col) => col.some((v) => v !== null)), [columns]);
  const titleId = `chart-${spec.id}-title`;

  useEffect(() => {
    const el = plotRef.current;
    if (!el) return;
    const colors = readColors();
    const segments = timelineSegments(result.phases, frames.n_frames);
    const [yMin, yMax] = yRange(columns, bands);
    const fps = frames.fps;
    const axis = {
      stroke: colors.muted,
      font: FONT,
      grid: { stroke: colors.grid, width: 1 },
      ticks: { show: false },
    };

    const u = new uPlot(
      {
        width: el.clientWidth || 320,
        height: HEIGHT,
        legend: { show: false },
        cursor: {
          sync: { key: "serve-charts" },
          y: false,
          drag: { x: false, y: false },
          points: { size: 7, fill: colors.ink, stroke: colors.ink },
        },
        scales: { x: { time: false }, y: { range: () => [yMin, yMax] } },
        axes: [
          { ...axis, size: 26, values: (_u, vals) => vals.map((v) => `${v.toFixed(1)}s`) },
          {
            ...axis,
            size: 42,
            values: (_u, vals) => vals.map((v) => (spec.unit === "°" ? `${Math.round(v)}°` : v.toFixed(1))),
          },
        ],
        series: [
          {},
          ...spec.series.map((s) => ({
            label: s.label,
            stroke: colors.ink,
            width: 2,
            dash: s.dash,
            spanGaps: false,
            points: { show: false },
          })),
        ],
        hooks: {
          drawClear: [
            (self: uPlot) => {
              drawPhaseShading(self, segments, fps, colors);
              drawBands(self, bands, fps, colors);
            },
          ],
          draw: [(self: uPlot) => drawPhasePoints(self, points, fps)],
        },
      },
      columns as uPlot.AlignedData,
      el,
    );

    const playhead = document.createElement("div");
    playhead.className = "chart-playhead";
    u.over.appendChild(playhead);

    const place = () => {
      const { frame } = store.getState();
      playhead.style.transform = `translateX(${u.valToPos(frame / fps, "x")}px)`;
      spec.series.forEach((s, i) => {
        const span = readoutRefs.current[i];
        if (span) span.textContent = formatMetric(s.metric, frames.series[s.metric][frame]);
      });
    };
    place();
    const unsubscribe = store.subscribe(place);

    const resize = new ResizeObserver(() => {
      if (el.clientWidth > 0) u.setSize({ width: el.clientWidth, height: HEIGHT });
      place();
    });
    resize.observe(el);

    let restoreTo: number | null = null;
    const frameAt = (e: PointerEvent) => u.posToIdx(e.offsetX);
    const onEnter = () => {
      restoreTo = store.getState().playing ? null : store.getState().frame;
    };
    const onMove = (e: PointerEvent) => {
      if (restoreTo !== null && e.pointerType === "mouse" && !store.getState().playing) store.seek(frameAt(e));
    };
    const onLeave = () => {
      if (restoreTo !== null && !store.getState().playing) store.seek(restoreTo);
      restoreTo = null;
    };
    const onDown = (e: PointerEvent) => {
      const frame = frameAt(e);
      store.seek(frame);
      restoreTo = store.getState().playing ? null : frame;
    };
    u.over.addEventListener("pointerenter", onEnter);
    u.over.addEventListener("pointermove", onMove);
    u.over.addEventListener("pointerleave", onLeave);
    u.over.addEventListener("pointerdown", onDown);

    return () => {
      unsubscribe();
      resize.disconnect();
      u.over.removeEventListener("pointerenter", onEnter);
      u.over.removeEventListener("pointermove", onMove);
      u.over.removeEventListener("pointerleave", onLeave);
      u.over.removeEventListener("pointerdown", onDown);
      u.destroy();
    };
  }, [columns, bands, points, spec, frames, result, store, theme]);

  return (
    <figure aria-labelledby={titleId} className="rounded-xl border border-border bg-surface p-3">
      <figcaption className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span id={titleId} className="text-sm font-semibold">
          {spec.title}
        </span>
        <span className="flex items-center gap-3 text-sm">
          {spec.series.map((s, i) => (
            <span key={s.metric} className="flex items-center gap-1.5">
              {spec.series.length > 1 && (
                <>
                  <svg width="18" height="6" aria-hidden className="text-ink">
                    <line x1="0" y1="3" x2="18" y2="3" stroke="currentColor" strokeWidth="2" strokeDasharray={s.dash?.join(" ")} />
                  </svg>
                  <span className="text-ink-muted">{s.label}</span>
                </>
              )}
              <span
                ref={(node) => {
                  readoutRefs.current[i] = node;
                }}
                className="tabular font-semibold"
                aria-hidden
              >
                —
              </span>
            </span>
          ))}
        </span>
      </figcaption>
      <p className="mb-1 text-xs text-ink-muted">{spec.description}</p>
      <div className="relative">
        <div ref={plotRef} className="w-full cursor-crosshair touch-pan-y" aria-hidden data-testid={`chart-${spec.id}`} />
        {!hasData && (
          <p className="pointer-events-none absolute inset-0 grid place-items-center p-4 text-center">
            <span className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink-muted shadow-sm">
              Not measured in this clip: the joints weren't visible clearly enough.
            </span>
          </p>
        )}
      </div>
      <p className="sr-only">
        {spec.series.map((s) => seriesSummary(frames, s)).join(" ")}
        {bands.length > 0 && " The shaded green band is the good range for each phase."}
      </p>
    </figure>
  );
}
