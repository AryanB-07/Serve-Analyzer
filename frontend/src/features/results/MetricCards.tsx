import type { AnalysisResult, MetricStatus } from "../../api/types";
import { StatusIcon, STATUS_TEXT } from "../../components/StatusIcon";
import { formatMetric } from "../../lib/chartData";
import { CARD_ORDER, METRIC_INFO, rangeBarLayout, readingFor, type MetricReading } from "../../lib/metricInfo";
import { PHASE_LABELS, segmentAt } from "../../lib/phases";
import { usePlayhead, usePlayheadStore } from "../../playhead/context";

const STATUS_BORDER: Record<MetricStatus, string> = {
  good: "border-l-good",
  borderline: "border-l-warn",
  off: "border-l-bad",
  unknown: "border-l-border",
};

export function statusLine(reading: MetricReading): string {
  if (reading.status === "unknown") return STATUS_TEXT.unknown;
  if (!reading.direction) return STATUS_TEXT[reading.status];
  const side = reading.direction === "low" ? "low" : "high";
  return `${STATUS_TEXT[reading.status]}: ${reading.status === "off" ? "too" : "a little"} ${side}`;
}

function RangeBar({ reading }: { reading: MetricReading }) {
  if (!reading.range) return null;
  const layout = rangeBarLayout(reading.value, reading.range);
  const [lo, hi] = reading.range.good;
  return (
    <div className="space-y-1">
      <div className="relative h-2 rounded-full bg-surface-2" aria-hidden>
        <div
          className="absolute inset-y-0 rounded-full bg-warn/30"
          style={{ left: `${layout.borderline[0]}%`, width: `${layout.borderline[1]}%` }}
        />
        <div
          className="absolute inset-y-0 rounded-full bg-good/60"
          style={{ left: `${layout.good[0]}%`, width: `${layout.good[1]}%` }}
        />
        {layout.marker !== null && (
          <div
            className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded-full bg-ink ring-2 ring-surface"
            style={{ left: `${layout.marker}%` }}
          />
        )}
      </div>
      <p className="text-xs text-ink-muted">
        Good range {formatMetric(reading.metric, lo)}–{formatMetric(reading.metric, hi)} at{" "}
        {PHASE_LABELS[reading.phase].toLowerCase()}
      </p>
    </div>
  );
}

export function MetricCard({ reading, phases }: { reading: MetricReading; phases: AnalysisResult["phases"] }) {
  const store = usePlayheadStore();
  const info = METRIC_INFO[reading.metric];
  const active = usePlayhead((s) => segmentAt(s.frame, phases) === reading.phase);
  const titleId = `metric-${reading.metric}`;
  const phaseLabel = PHASE_LABELS[reading.phase];

  return (
    <article
      aria-labelledby={titleId}
      className={`space-y-2.5 rounded-xl border border-l-4 border-border bg-surface p-3.5 transition-shadow ${
        STATUS_BORDER[reading.status]
      } ${active ? "ring-2 ring-accent/60" : ""}`}
      data-testid={`metric-card-${reading.metric}`}
    >
      <header className="flex items-start justify-between gap-2">
        <h3 id={titleId} className="text-sm font-semibold">
          {info.title}
        </h3>
        <span className="inline-flex items-center gap-1.5 text-xs font-medium" data-testid="metric-status">
          <StatusIcon status={reading.status} className="size-3" />
          {statusLine(reading)}
        </span>
      </header>
      <p className="flex items-baseline gap-2">
        <span className="tabular text-2xl font-semibold tracking-tight">{formatMetric(reading.metric, reading.value)}</span>
        <span className="text-sm text-ink-muted">at {phaseLabel.toLowerCase()}</span>
      </p>
      <RangeBar reading={reading} />
      <p className="text-sm text-ink-muted">{info.explanation}</p>
      {reading.frame !== null ? (
        <button
          type="button"
          onClick={() => store.seek(reading.frame!)}
          className="text-sm font-medium text-accent hover:underline"
        >
          Jump to {phaseLabel.toLowerCase()} · {(reading.frame / store.fps).toFixed(2)}s
        </button>
      ) : (
        <p className="text-sm text-ink-muted">{phaseLabel} wasn't detected in this clip.</p>
      )}
    </article>
  );
}

export function MetricCards({ result }: { result: AnalysisResult }) {
  const readings = CARD_ORDER.map((metric) => readingFor(metric, result));
  return (
    <section aria-labelledby="metrics-heading" className="space-y-3">
      <h2 id="metrics-heading" className="text-lg font-semibold">
        Key positions
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
        {readings.map((reading) => (
          <MetricCard key={reading.metric} reading={reading} phases={result.phases} />
        ))}
      </div>
    </section>
  );
}
