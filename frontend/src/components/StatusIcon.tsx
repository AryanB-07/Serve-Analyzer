import type { MetricStatus } from "../api/types";

export const STATUS_TEXT: Record<MetricStatus, string> = {
  good: "Good",
  borderline: "Borderline",
  off: "Needs work",
  unknown: "Not measured",
};

const COLOR_CLASS: Record<MetricStatus, string> = {
  good: "text-good",
  borderline: "text-warn",
  off: "text-bad",
  unknown: "text-neutral",
};

/** Shape matches the on-video marker: circle, triangle, diamond, dashed ring. */
export function StatusIcon({ status, className = "size-3.5" }: { status: MetricStatus; className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={`${COLOR_CLASS[status]} ${className} shrink-0`} aria-hidden>
      {status === "good" && <circle cx="8" cy="8" r="6" fill="currentColor" />}
      {status === "borderline" && <path d="M8 1.8 14.6 13.6H1.4Z" fill="currentColor" />}
      {status === "off" && <path d="M8 1 15 8 8 15 1 8Z" fill="currentColor" />}
      {status === "unknown" && (
        <circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeDasharray="2.5 2" />
      )}
    </svg>
  );
}

export function StatusBadge({ status }: { status: MetricStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium">
      <StatusIcon status={status} />
      {STATUS_TEXT[status]}
    </span>
  );
}
