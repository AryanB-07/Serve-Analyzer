import type { AnalysisResult, MetricName, MetricStatus } from "../../api/types";
import { StatusIcon, STATUS_TEXT } from "../../components/StatusIcon";
import { formatMetric } from "../../lib/chartData";
import { likelyRange, uncertaintyFor, type Uncertainty } from "../../lib/confidence";
import { CARD_ORDER, METRIC_INFO, rangeBarLayout, readingFor, type MetricReading } from "../../lib/metricInfo";
import { PHASE_LABELS, segmentAt } from "../../lib/phases";
import { bandOf, overallScore, scoreFor, SCORE_BANDS } from "../../lib/score";
import type { ResultsMode } from "../../lib/useResultsMode";
import { usePlayhead, usePlayheadStore } from "../../playhead/context";
import { CameraNote } from "./CameraNote";

const STATUS_BORDER: Record<MetricStatus, string> = {
  good: "border-l-good",
  borderline: "border-l-warn",
  off: "border-l-bad",
  unknown: "border-l-border",
};

/** Simple mode's score numbers, coloured by band (all 5:1 or more on the card in both themes). */
export const SCORE_TEXT: Record<"good" | "borderline" | "off", string> = {
  good: "text-good",
  borderline: "text-warn",
  off: "text-bad",
};

const BAND_COLOUR: Record<"good" | "borderline" | "off", string> = {
  good: "bg-good/60",
  borderline: "bg-warn/40",
  off: "bg-bad/35",
};

export const UNREADABLE_TEXT = "Can't be read from this angle";

export function statusLine(reading: MetricReading): string {
  if (reading.quality === "unreadable") return UNREADABLE_TEXT;
  if (reading.status === "unknown") return STATUS_TEXT.unknown;
  if (!reading.direction) return STATUS_TEXT[reading.status];
  const side = reading.direction === "low" ? "low" : "high";
  return `${STATUS_TEXT[reading.status]}: ${reading.status === "off" ? "too" : "a little"} ${side}`;
}

/** Advanced mode's precision: angles to 0.1°, height to 0.01 body heights. */
export function formatExact(metric: MetricName, value: number | null): string {
  if (value === null) return "—";
  return metric === "wrist_height" ? `${value.toFixed(2)}×` : `${value.toFixed(1)}°`;
}

function formatMargin(metric: MetricName, margin: number): string {
  return metric === "wrist_height" ? `±${margin.toFixed(2)}` : `±${margin.toFixed(1)}°`;
}

const pct = (x: number, [min, max]: [number, number]) => Math.min(100, Math.max(0, ((x - min) / (max - min || 1)) * 100));

/** Advanced mode's slider: the reference range, the value, and the likely range around it. */
function RangeBar({ reading, likely }: { reading: MetricReading; likely: [number, number] | null }) {
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
        {likely && (
          <div
            data-testid="likely-band"
            className="absolute -inset-y-1 rounded-sm border border-ink/40 bg-ink/10"
            style={{ left: `${pct(likely[0], layout.domain)}%`, width: `${pct(likely[1], layout.domain) - pct(likely[0], layout.domain)}%` }}
          />
        )}
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

/** Simple mode's slider: the same bar, on the 0-100 score scale. */
export function ScoreBar({ score, label }: { score: number; label: string }) {
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score}
      aria-valuetext={`${score} out of 100, ${STATUS_TEXT[bandOf(score)].toLowerCase()}`}
      className="relative h-2 rounded-full bg-surface-2"
    >
      {SCORE_BANDS.map((b) => (
        <div
          key={b.status}
          className={`absolute inset-y-0 ${BAND_COLOUR[b.status]} ${b.from === 0 ? "rounded-l-full" : ""} ${b.to === 100 ? "rounded-r-full" : ""}`}
          style={{ left: `${b.from}%`, width: `${b.to - b.from}%` }}
        />
      ))}
      <div
        className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded-full bg-ink ring-2 ring-surface"
        style={{ left: `${score}%` }}
      />
    </div>
  );
}

function ConfidenceDetails({ reading, u, likely }: { reading: MetricReading; u: Uncertainty | null; likely: [number, number] | null }) {
  if (!u) {
    return <p className="text-xs text-ink-muted">Confidence details aren't available for this analysis.</p>;
  }
  const levelText = { high: "high", medium: "medium", low: "low" } as const;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 rounded-lg bg-bg/60 px-2.5 py-2 text-xs" data-testid="confidence">
      {likely && (
        <>
          <dt className="text-ink-muted">Likely range</dt>
          <dd className="tabular font-medium">
            {formatExact(reading.metric, likely[0])} to {formatExact(reading.metric, likely[1])}
            <span className="font-normal text-ink-muted"> ({formatMargin(reading.metric, u.margin!)})</span>
          </dd>
        </>
      )}
      <dt className="text-ink-muted">Tracking confidence</dt>
      <dd className="tabular">
        {u.visibility === null ? "—" : `${Math.round(u.visibility * 100)}%`}
        {u.level && <span className="text-ink-muted"> · {levelText[u.level]}</span>}
      </dd>
      <dt className="text-ink-muted">Tracking noise</dt>
      <dd className="tabular">{u.noise === null ? "—" : formatMargin(reading.metric, u.noise)}</dd>
      <dt className="text-ink-muted">Camera angle error</dt>
      <dd className="tabular">
        {u.cameraError === null ? "—" : `up to ${formatMargin(reading.metric, u.cameraError)}`}
        <span className="text-ink-muted">
          {" "}
          {u.assumed ? "if filmed side-on, as the guide says" : "from your camera position"}
        </span>
      </dd>
    </dl>
  );
}

export function MetricCard({
  reading,
  phases,
  mode = "advanced",
  uncertainty = null,
}: {
  reading: MetricReading;
  phases: AnalysisResult["phases"];
  mode?: ResultsMode;
  uncertainty?: Uncertainty | null;
}) {
  const store = usePlayheadStore();
  const info = METRIC_INFO[reading.metric];
  const active = usePlayhead((s) => segmentAt(s.frame, phases) === reading.phase);
  const titleId = `metric-${reading.metric}`;
  const phaseLabel = PHASE_LABELS[reading.phase];
  const unreadable = reading.quality === "unreadable";
  const approximate = reading.quality === "approximate" && reading.value !== null;
  const score = unreadable ? null : scoreFor(reading.value, reading.range);
  const likely = unreadable ? null : likelyRange(reading.value, uncertainty);

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
          {mode === "simple" && !unreadable && reading.status !== "unknown" ? STATUS_TEXT[reading.status] : statusLine(reading)}
        </span>
      </header>
      {unreadable ? (
        <p className="text-sm text-ink-muted">
          Your camera position can't see this clearly enough to score it, so it has no feedback.
        </p>
      ) : mode === "simple" ? (
        score === null ? (
          <p className="text-sm text-ink-muted">Not measured in this clip.</p>
        ) : (
          <>
            <p className="flex flex-wrap items-baseline gap-x-1.5">
              <span className={`tabular text-3xl font-semibold tracking-tight ${SCORE_TEXT[bandOf(score)]}`} data-testid="score" data-band={bandOf(score)}>
                {approximate && <span aria-hidden>≈</span>}
                {score}
              </span>
              <span className="text-sm text-ink-muted">/ 100</span>
              {approximate && <span className="ml-1 rounded-full border border-border px-2 text-xs text-ink-muted">rough from this angle</span>}
            </p>
            <ScoreBar score={score} label={`${info.title} score`} />
          </>
        )
      ) : (
        <>
          <p className="flex flex-wrap items-baseline gap-x-2">
            <span className="tabular text-2xl font-semibold tracking-tight">
              {approximate && <span aria-hidden>≈</span>}
              {formatExact(reading.metric, reading.value)}
            </span>
            <span className="text-sm text-ink-muted">at {phaseLabel.toLowerCase()}</span>
            {approximate && (
              <span className="rounded-full border border-border px-2 text-xs text-ink-muted">approximate from this angle</span>
            )}
          </p>
          <RangeBar reading={reading} likely={likely} />
          {reading.value !== null && <ConfidenceDetails reading={reading} u={uncertainty} likely={likely} />}
        </>
      )}
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

/** Simple mode's headline: the average of the key positions' scores. */
function OverallScore({ scores }: { scores: (number | null)[] }) {
  const overall = overallScore(scores);
  const counted = scores.filter((s) => s !== null).length;
  if (overall === null) return null;
  return (
    <section aria-labelledby="overall-heading" className="space-y-2 rounded-xl border border-border bg-surface p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 id="overall-heading" className="text-sm font-semibold">Serve score</h3>
        <span className="inline-flex items-center gap-1.5 text-xs font-medium">
          <StatusIcon status={bandOf(overall)} className="size-3" />
          {STATUS_TEXT[bandOf(overall)]}
        </span>
      </div>
      <p className="flex items-baseline gap-1.5">
        <span className={`tabular text-4xl font-semibold tracking-tight ${SCORE_TEXT[bandOf(overall)]}`} data-testid="overall-score" data-band={bandOf(overall)}>{overall}</span>
        <span className="text-sm text-ink-muted">/ 100</span>
      </p>
      <ScoreBar score={overall} label="Serve score" />
      <p className="text-xs text-ink-muted">
        The average of {counted} key {counted === 1 ? "position" : "positions"}, against general reference ranges, not a
        coach's judgement.
      </p>
    </section>
  );
}

export function MetricCards({ result, mode = "advanced" }: { result: AnalysisResult; mode?: ResultsMode }) {
  const readings = CARD_ORDER.map((metric) => readingFor(metric, result));
  const scores = readings.map((r) => (r.quality === "unreadable" ? null : scoreFor(r.value, r.range)));
  return (
    <section aria-labelledby="metrics-heading" className="space-y-3">
      <h2 id="metrics-heading" className="text-lg font-semibold">
        Key positions
      </h2>
      {mode === "simple" && <OverallScore scores={scores} />}
      <CameraNote result={result} mode={mode} />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
        {readings.map((reading) => (
          <MetricCard
            key={reading.metric}
            reading={reading}
            phases={result.phases}
            mode={mode}
            uncertainty={uncertaintyFor(result, reading.phase, reading.metric)}
          />
        ))}
      </div>
    </section>
  );
}
