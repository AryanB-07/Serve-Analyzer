import { useParams } from "react-router";

import { useAnalysis, useFrames, useResult } from "../../api/queries";

/** Milestone 2 placeholder: proves result + frames load. Replaced in milestone 3. */
export function ResultsPage() {
  const { id = "" } = useParams();
  const analysis = useAnalysis(id);
  const succeeded = analysis.data?.status === "succeeded";
  const result = useResult(id, succeeded);
  const frames = useFrames(id, succeeded);

  if (analysis.isError) return <p role="alert">Could not load this analysis: {analysis.error.message}</p>;
  if (!analysis.data) return <p>Loading…</p>;
  if (!succeeded) return <p>Status: {analysis.data.status}</p>;
  if (!result.data || !frames.data) return <p>Loading results…</p>;

  const r = result.data;
  const f = frames.data;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{analysis.data.filename}</h1>
      <video src={r.video_url} controls playsInline className="w-full max-w-3xl rounded-xl bg-black" />
      <dl className="grid max-w-3xl grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        {[
          ["Frames", f.n_frames],
          ["FPS", r.fps],
          ["Trophy", r.phases.trophy ?? "—"],
          ["Contact", r.phases.contact ?? "—"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-border bg-surface p-3">
            <dt className="text-ink-muted">{label}</dt>
            <dd className="tabular text-lg font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
