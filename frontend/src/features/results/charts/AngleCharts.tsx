import { useId, useState } from "react";

import type { AnalysisResult, FramesPayload, MetricName } from "../../../api/types";
import { CHARTS, formatMetric } from "../../../lib/chartData";
import { SEGMENT_LABELS, segmentAt } from "../../../lib/phases";
import { usePlayheadStore } from "../../../playhead/context";
import { AngleChart } from "./AngleChart";

const TABLE_METRICS: [MetricName, string][] = [
  ["front_knee_flexion", "Front knee"],
  ["back_knee_flexion", "Back knee"],
  ["elbow_angle", "Elbow"],
  ["trunk_tilt", "Trunk"],
  ["wrist_height", "Wrist height"],
];

/** Every frame's values; rendered only when opened. Time cells seek the video. */
function DataTable({ frames, result }: { frames: FramesPayload; result: AnalysisResult }) {
  const store = usePlayheadStore();
  return (
    <div className="max-h-80 overflow-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <caption className="sr-only">Metric values for every frame</caption>
        <thead className="sticky top-0 bg-surface-2 text-left">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">Time</th>
            <th scope="col" className="px-3 py-2 font-medium">Phase</th>
            {TABLE_METRICS.map(([m, label]) => (
              <th key={m} scope="col" className="px-3 py-2 text-right font-medium">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {Array.from({ length: frames.n_frames }, (_, f) => (
            <tr key={f} className="border-t border-border">
              <th scope="row" className="px-3 py-1 text-left font-normal">
                <button type="button" onClick={() => store.seek(f)} className="text-accent hover:underline">
                  {(f / frames.fps).toFixed(2)}s
                </button>
              </th>
              <td className="px-3 py-1 text-ink-muted">{SEGMENT_LABELS[segmentAt(f, result.phases)]}</td>
              {TABLE_METRICS.map(([m]) => (
                <td key={m} className="px-3 py-1 text-right">{formatMetric(m, frames.series[m][f])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AngleCharts({ frames, result }: { frames: FramesPayload; result: AnalysisResult }) {
  const [showTable, setShowTable] = useState(false);
  const tableId = useId();
  return (
    <section aria-labelledby="charts-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="charts-heading" className="text-lg font-semibold">Angles over time</h2>
          <p className="text-sm text-ink-muted">
            Shaded regions are phases; green bands are the reference range for each phase. Hover to preview, click to jump.
          </p>
        </div>
        <button
          type="button"
          aria-expanded={showTable}
          aria-controls={tableId}
          onClick={() => setShowTable(!showTable)}
          className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-ink-muted hover:text-ink"
        >
          {showTable ? "Hide data table" : "View as table"}
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {CHARTS.map((spec) => (
          <AngleChart key={spec.id} spec={spec} frames={frames} result={result} />
        ))}
      </div>
      <div id={tableId}>{showTable && <DataTable frames={frames} result={result} />}</div>
    </section>
  );
}
