import { useState } from "react";
import { useParams } from "react-router";

import { useAnalysis, useFrames, useResult } from "../../api/queries";
import type { AnalysisResult, AnalysisSummary, FramesPayload } from "../../api/types";
import { PlayheadProvider } from "../../playhead/context";
import { OverlayToggles } from "./OverlayToggles";
import { PlayheadReadout } from "./PlayheadReadout";
import { VideoStage, type OverlayOptions } from "./VideoStage";

const DEFAULT_OPTIONS: OverlayOptions = { showSkeleton: true, showLabels: true, source: "smoothed" };

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
      <div className="space-y-5">
        <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{summary.filename}</h1>
          <p className="text-sm text-ink-muted">
            {new Date(summary.created_at).toLocaleDateString(undefined, { dateStyle: "medium" })} ·{" "}
            {result.hand === "right" ? "Right" : "Left"}-handed · {result.fps} fps
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <section aria-label="Video" className="space-y-3">
            <VideoStage result={result} frames={frames} options={options} controls />
            <PlayheadReadout phases={result.phases} nFrames={frames.n_frames} fps={frames.fps} />
            <OverlayToggles options={options} onChange={setOptions} />
          </section>

          <aside aria-label="Notes" className="space-y-3">
            {result.warnings.length > 0 && (
              <div className="rounded-xl border border-warn/40 bg-surface p-4">
                <h2 className="mb-2 text-sm font-semibold text-warn">Heads up</h2>
                <ul className="list-disc space-y-1 pl-5 text-sm text-ink-muted">
                  {result.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </aside>
        </div>
      </div>
    </PlayheadProvider>
  );
}

export function ResultsPage() {
  const { id = "" } = useParams();
  const analysis = useAnalysis(id);
  const succeeded = analysis.data?.status === "succeeded";
  const result = useResult(id, succeeded);
  const frames = useFrames(id, succeeded);

  if (analysis.isError) return <p role="alert">Could not load this analysis: {analysis.error.message}</p>;
  if (!analysis.data) return <p>Loading…</p>;
  if (!succeeded) return <p>Status: {analysis.data.status}</p>;
  if (result.isError || frames.isError) return <p role="alert">Could not load the results.</p>;
  if (!result.data || !frames.data) return <p>Loading results…</p>;

  return <ResultsView key={id} summary={analysis.data} result={result.data} frames={frames.data} />;
}
