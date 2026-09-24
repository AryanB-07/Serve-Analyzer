import { useMemo } from "react";

import type { AnalysisResult, FramesPayload } from "../../../api/types";
import { formatMetric, phasePoints, referenceBands, seriesSummary, type ChartSpec } from "../../../lib/chartData";
import { TimeSeriesChart, type LineSeries } from "./TimeSeriesChart";

/** One metric chart for a single analysis. */
export function AngleChart({ spec, frames, result }: { spec: ChartSpec; frames: FramesPayload; result: AnalysisResult }) {
  const lines = useMemo<LineSeries[]>(
    () =>
      spec.series.map((s) => ({
        key: s.metric,
        label: s.label,
        values: frames.series[s.metric],
        tone: "ink",
        dash: s.dash,
        format: (v) => formatMetric(s.metric, v),
      })),
    [spec, frames],
  );
  const bands = useMemo(
    () => referenceBands(spec, result.ranges, result.phases, frames.n_frames),
    [spec, result, frames.n_frames],
  );
  const points = useMemo(() => phasePoints(spec, result), [spec, result]);
  const summary =
    spec.series.map((s) => seriesSummary(frames, s)).join(" ") +
    (bands.length > 0 ? " The shaded green band is the good range for each phase." : "");

  return (
    <TimeSeriesChart
      id={spec.id}
      title={spec.title}
      description={spec.description}
      unit={spec.unit}
      fps={frames.fps}
      nFrames={frames.n_frames}
      phases={result.phases}
      lines={lines}
      bands={bands}
      points={points}
      summary={summary}
    />
  );
}
