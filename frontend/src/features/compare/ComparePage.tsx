import { useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { useAnalysis, useFrames, useResult } from "../../api/queries";
import type { AnalysisResult, AnalysisSummary, FramesPayload } from "../../api/types";
import { StatusIcon } from "../../components/StatusIcon";
import { phaseAnchors, resampleOnto, type Anchor, type ClipTiming, type PhaseAnchor } from "../../lib/align";
import { CHARTS, formatMetric, referenceBands } from "../../lib/chartData";
import { compareMetric, type Change } from "../../lib/compare";
import { CARD_ORDER, METRIC_INFO, readingFor } from "../../lib/metricInfo";
import { PHASE_LABELS } from "../../lib/phases";
import { PlayheadProvider, usePlayheadStore } from "../../playhead/context";
import type { PlayheadStore } from "../../playhead/store";
import { useFollowerVideo } from "../../playhead/useFollowerVideo";
import { TimeSeriesChart, type LineSeries } from "../results/charts/TimeSeriesChart";
import { FrameControls } from "../results/FrameControls";
import { OverlayToggles } from "../results/OverlayToggles";
import { PhaseTimeline } from "../results/PhaseTimeline";
import { CurrentPhase, FrameCounter, StatusKey } from "../results/PlayheadReadout";
import { useKeyboardShortcuts } from "../results/useKeyboardShortcuts";
import { VideoStage, type OverlayOptions } from "../results/VideoStage";

interface Clip {
  summary: AnalysisSummary;
  result: AnalysisResult;
  frames: FramesPayload;
  timing: ClipTiming;
}

const DEFAULT_OPTIONS: OverlayOptions = { showSkeleton: true, showLabels: false, source: "smoothed" };

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}

function alignmentNote(anchors: PhaseAnchor[]): string {
  if (anchors.length === 0) {
    return "No phase was detected in both clips, so the videos simply play from their starts.";
  }
  const joined = anchors.map((x) => PHASE_LABELS[x.phase].toLowerCase()).join(" and ");
  return anchors.length === 1
    ? `Aligned at ${joined}: the after video is shifted in time so that moment lines up.`
    : `Aligned at ${joined}: between them the after video speeds up or slows down so both hit each phase together.`;
}

function ClipPanel({ label, clip, children }: { label: string; clip: Clip; children: ReactNode }) {
  return (
    <section aria-label={`${label}: ${clip.summary.filename}`} className="min-w-0 space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-sm font-semibold">{label}</span>
        <Link to={`/analyses/${clip.summary.id}`} className="truncate text-sm hover:underline">
          {clip.summary.filename}
        </Link>
        <span className="text-sm text-ink-muted">{formatDate(clip.summary.created_at)}</span>
      </div>
      {children}
    </section>
  );
}

function FollowerStage({
  master,
  a,
  b,
  anchors,
  options,
}: {
  master: PlayheadStore;
  a: Clip;
  b: Clip;
  anchors: Anchor[];
  options: OverlayOptions;
}) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  useFollowerVideo(video, master, a.timing, b.timing, anchors);
  return (
    <>
      <VideoStage result={b.result} frames={b.frames} options={options} muted onVideoElement={setVideo} onVideoClick={master.togglePlay} />
      <div className="flex flex-wrap items-center gap-3">
        <CurrentPhase phases={b.result.phases} />
        <FrameCounter />
      </div>
    </>
  );
}

const CHANGE_TEXT: Record<Change, { text: string; className: string }> = {
  better: { text: "Improved", className: "text-good" },
  worse: { text: "Worse", className: "text-bad" },
  same: { text: "About the same", className: "text-ink-muted" },
  "n/a": { text: "—", className: "text-ink-muted" },
};

function ComparisonTable({ a, b }: { a: Clip; b: Clip }) {
  return (
    <section aria-labelledby="compare-table-heading" className="space-y-3">
      <h2 id="compare-table-heading" className="text-lg font-semibold">Key positions, before and after</h2>
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm">
          <caption className="sr-only">Each metric at its key phase in both clips, and whether it moved toward the good range</caption>
          <thead className="bg-surface-2 text-left">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">Metric</th>
              <th scope="col" className="hidden px-3 py-2 font-medium sm:table-cell">Good range</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Before</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">After</th>
              <th scope="col" className="px-3 py-2 font-medium">Change</th>
            </tr>
          </thead>
          <tbody>
            {CARD_ORDER.map((metric) => {
              const ra = readingFor(metric, a.result);
              const rb = readingFor(metric, b.result);
              const range = ra.range ?? rb.range;
              const change = CHANGE_TEXT[compareMetric(ra.value, rb.value, range)];
              return (
                <tr key={metric} className="border-t border-border bg-surface">
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    {METRIC_INFO[metric].title}
                    <span className="block text-xs font-normal text-ink-muted">at {PHASE_LABELS[ra.phase].toLowerCase()}</span>
                  </th>
                  <td className="tabular hidden px-3 py-2 text-ink-muted sm:table-cell">
                    {range ? `${formatMetric(metric, range.good[0])}–${formatMetric(metric, range.good[1])}` : "—"}
                  </td>
                  {[ra, rb].map((r, i) => (
                    <td key={i} className="tabular px-3 py-2 text-right">
                      <span className="inline-flex items-center gap-1.5">
                        <StatusIcon status={r.status} className="size-3" />
                        {formatMetric(metric, r.value)}
                      </span>
                    </td>
                  ))}
                  <td className={`px-3 py-2 font-medium ${change.className}`}>{change.text}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CompareCharts({ a, b, anchors }: { a: Clip; b: Clip; anchors: Anchor[] }) {
  const charts = useMemo(
    () =>
      CHARTS.map((spec) => {
        const primary = spec.series[0]!;
        const lines: LineSeries[] = [
          {
            key: "before",
            label: "Before",
            values: a.frames.series[primary.metric],
            tone: "muted",
            dash: [6, 4],
            format: (v) => formatMetric(primary.metric, v),
          },
          {
            key: "after",
            label: "After",
            values: resampleOnto(b.frames.series[primary.metric], a.timing, b.timing, anchors),
            tone: "accent",
            format: (v) => formatMetric(primary.metric, v),
          },
        ];
        return {
          spec,
          title: spec.series.length > 1 ? `${primary.label} flexion` : spec.title,
          lines,
          bands: referenceBands(spec, a.result.ranges, a.result.phases, a.frames.n_frames),
        };
      }),
    [a, b, anchors],
  );
  return (
    <section aria-labelledby="compare-charts-heading" className="space-y-3">
      <div>
        <h2 id="compare-charts-heading" className="text-lg font-semibold">Angles over time, overlaid</h2>
        <p className="text-sm text-ink-muted">
          Plotted on the before clip's timeline; the after clip is time-aligned to it by phase. Dashed is before, solid is after.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {charts.map(({ spec, title, lines, bands }) => (
          <TimeSeriesChart
            key={spec.id}
            id={`compare-${spec.id}`}
            title={title}
            description={spec.description}
            unit={spec.unit}
            fps={a.frames.fps}
            nFrames={a.frames.n_frames}
            phases={a.result.phases}
            lines={lines}
            bands={bands}
            points={[]}
            summary={`${title}: before and after, aligned by phase.`}
            emptyMessage="Not measured in either clip."
          />
        ))}
      </div>
    </section>
  );
}

function Shortcuts({ phases }: { phases: AnalysisResult["phases"] }) {
  useKeyboardShortcuts(usePlayheadStore(), phases);
  return null;
}

function CompareBody({ a, b }: { a: Clip; b: Clip }) {
  const master = usePlayheadStore();
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  const anchors = useMemo(() => phaseAnchors(a.timing, b.timing), [a.timing, b.timing]);
  return (
    <div className="space-y-8">
      <Shortcuts phases={a.result.phases} />
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Compare serves</h1>
        <p className="text-sm text-ink-muted" data-testid="alignment-note">{alignmentNote(anchors)}</p>
      </header>

      <div className="space-y-3">
        <div className="grid gap-4 md:grid-cols-2">
          <ClipPanel label="Before" clip={a}>
            <VideoStage result={a.result} frames={a.frames} options={options} muted />
            <div className="flex flex-wrap items-center gap-3">
              <CurrentPhase phases={a.result.phases} />
              <FrameCounter />
            </div>
          </ClipPanel>
          <PlayheadProvider nFrames={b.frames.n_frames} fps={b.frames.fps}>
            <ClipPanel label="After" clip={b}>
              <FollowerStage master={master} a={a} b={b} anchors={anchors} options={options} />
            </ClipPanel>
          </PlayheadProvider>
        </div>
        <FrameControls />
        <PhaseTimeline phases={a.result.phases} />
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
          <OverlayToggles options={options} onChange={setOptions} />
          <StatusKey />
        </div>
      </div>

      <ComparisonTable a={a} b={b} />
      <CompareCharts a={a} b={b} anchors={anchors} />
    </div>
  );
}

function useClip(id: string): { clip: Clip | null; error: string | null } {
  const summary = useAnalysis(id);
  const ready = summary.data?.status === "succeeded";
  const result = useResult(id, ready);
  const frames = useFrames(id, ready);
  const clip = useMemo(() => {
    if (!summary.data || !result.data || !frames.data) return null;
    const timing = { phases: result.data.phases, fps: frames.data.fps, nFrames: frames.data.n_frames };
    return { summary: summary.data, result: result.data, frames: frames.data, timing };
  }, [summary.data, result.data, frames.data]);
  let error: string | null = null;
  if (summary.isError || result.isError || frames.isError) error = "One of these analyses couldn't be loaded.";
  else if (summary.data && summary.data.status !== "succeeded") {
    error = `"${summary.data.filename}" isn't ready to compare (it is ${summary.data.status.replace("_", " ")}).`;
  }
  return { clip, error };
}

function Message({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-xl space-y-3 rounded-2xl border border-border bg-surface p-8 text-center">
      {children}
      <Link to="/history" className="inline-block rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent">
        Choose from history
      </Link>
    </div>
  );
}

export function ComparePage() {
  const [params] = useSearchParams();
  const aId = params.get("a") ?? "";
  const bId = params.get("b") ?? "";
  const a = useClip(aId);
  const b = useClip(bId);

  if (!aId || !bId || aId === bId) return <Message><p>Pick two different serves to compare.</p></Message>;
  const error = a.error ?? b.error;
  if (error) return <Message><p>{error}</p></Message>;
  if (!a.clip || !b.clip) return <p className="text-center text-ink-muted">Loading both serves…</p>;

  return (
    <PlayheadProvider key={`${aId}-${bId}`} nFrames={a.clip.frames.n_frames} fps={a.clip.frames.fps}>
      <CompareBody a={a.clip} b={b.clip} />
    </PlayheadProvider>
  );
}
