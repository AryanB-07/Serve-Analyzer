import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { api, ApiError } from "../../api";
import { queryKeys, useAnalysis, useFrames, useResult } from "../../api/queries";
import type { AnalysisResult, AnalysisSummary, FramesPayload } from "../../api/types";
import { PlayheadProvider, usePlayheadStore } from "../../playhead/context";
import { ProcessingView } from "../processing/ProcessingView";
import { AngleCharts } from "./charts/AngleCharts";
import { FeedbackPanel } from "./FeedbackPanel";
import { FrameControls } from "./FrameControls";
import { MetricCards } from "./MetricCards";
import { OverlayToggles } from "./OverlayToggles";
import { PhaseTimeline } from "./PhaseTimeline";
import { CurrentPhase, FrameCounter, StatusKey } from "./PlayheadReadout";
import { useKeyboardShortcuts } from "./useKeyboardShortcuts";
import { VideoStage, type OverlayOptions } from "./VideoStage";

const DEFAULT_OPTIONS: OverlayOptions = { showSkeleton: true, showLabels: true, source: "smoothed" };

function KeyboardShortcuts({ result }: { result: AnalysisResult }) {
  useKeyboardShortcuts(usePlayheadStore(), result.phases);
  return null;
}

function ResultsView({
  summary,
  result,
  frames,
}: {
  summary: AnalysisSummary;
  result: AnalysisResult;
  frames: FramesPayload;
}) {
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  return (
    <PlayheadProvider nFrames={frames.n_frames} fps={frames.fps}>
      <KeyboardShortcuts result={result} />
      <div className="space-y-5">
        <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{summary.filename}</h1>
          <p className="text-sm text-ink-muted">
            {new Date(summary.created_at).toLocaleDateString(undefined, { dateStyle: "medium" })} ·{" "}
            {result.hand === "right" ? "Right" : "Left"}-handed · {result.fps} fps
          </p>
        </header>

        {/* Phone order is DOM order (video, analysis, charts); on large screens the
            analysis column sits beside both. */}
        <div className="grid gap-x-6 gap-y-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:grid-rows-[auto_1fr]">
          <section aria-label="Video" className="min-w-0 space-y-3 lg:col-start-1">
            <VideoStage result={result} frames={frames} options={options} />
            <FrameControls>
              <CurrentPhase phases={result.phases} />
              <FrameCounter />
            </FrameControls>
            <PhaseTimeline phases={result.phases} />
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
              <OverlayToggles options={options} onChange={setOptions} />
              <StatusKey />
            </div>
          </section>

          <aside aria-label="Analysis" className="space-y-6 lg:col-start-2 lg:row-span-2 lg:row-start-1">
            <FeedbackPanel result={result} />
            <MetricCards result={result} />
            {result.warnings.length > 0 && (
              <div className="rounded-xl border border-warn/40 bg-surface p-4">
                <h2 className="mb-2 text-sm font-semibold text-warn">About this clip</h2>
                <ul className="list-disc space-y-1 pl-5 text-sm text-ink-muted">
                  {result.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </aside>

          <div className="min-w-0 lg:col-start-1">
            <AngleCharts frames={frames} result={result} />
          </div>
        </div>
      </div>
    </PlayheadProvider>
  );
}

function Processing({ summary }: { summary: AnalysisSummary }) {
  const queryClient = useQueryClient();
  const [since, setSince] = useState(() => Date.parse(summary.created_at));
  const retry = useMutation({
    mutationFn: () => api.retryAnalysis(summary.id),
    onSuccess: (next) => {
      setSince(Date.now());
      // New data with a non-terminal status restarts the status query's polling.
      queryClient.setQueryData(queryKeys.analysis(summary.id), next);
    },
  });
  return (
    <ProcessingView
      summary={summary}
      since={since}
      onRetry={() => retry.mutate()}
      retrying={retry.isPending}
      retryError={retry.error?.message ?? null}
    />
  );
}

function CenteredMessage({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mx-auto max-w-xl space-y-3 rounded-2xl border border-border bg-surface p-8 text-center">
      <h1 className="text-xl font-semibold">{title}</h1>
      {children}
    </div>
  );
}

export function ResultsPage() {
  const { id = "" } = useParams();
  const analysis = useAnalysis(id);
  const succeeded = analysis.data?.status === "succeeded";
  const result = useResult(id, succeeded);
  const frames = useFrames(id, succeeded);

  if (analysis.isError && !analysis.data) {
    const notFound = analysis.error instanceof ApiError && analysis.error.status === 404;
    return (
      <CenteredMessage title={notFound ? "We couldn't find that analysis" : "We couldn't load this analysis"}>
        <p className="text-ink-muted">{notFound ? "It may have been deleted, or the link is wrong." : analysis.error.message}</p>
        <div className="flex justify-center gap-3">
          {!notFound && (
            <button type="button" onClick={() => analysis.refetch()} className="rounded-lg border border-border px-4 py-2 font-medium">
              Try again
            </button>
          )}
          <Link to="/history" className="rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent">Go to history</Link>
        </div>
      </CenteredMessage>
    );
  }
  if (!analysis.data) return <CenteredMessage title="Loading…" />;
  if (!succeeded) return <Processing key={id} summary={analysis.data} />;
  if (result.isError || frames.isError) {
    return (
      <CenteredMessage title="We couldn't load the results">
        <button
          type="button"
          onClick={() => {
            void result.refetch();
            void frames.refetch();
          }}
          className="rounded-lg border border-border px-4 py-2 font-medium"
        >
          Try again
        </button>
      </CenteredMessage>
    );
  }
  if (!result.data || !frames.data) return <CenteredMessage title="Loading results…" />;

  return <ResultsView key={id} summary={analysis.data} result={result.data} frames={frames.data} />;
}
