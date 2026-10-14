import type { AnalysisResult, MetricName, MetricStatus, PhaseName } from "../api/types";

/**
 * Where the person said the camera was (asked at upload), and what that position can read.
 * The server rates each measurement "measured", "approximate" or "unreadable" from the synthetic
 * camera rig (serve_analyzer/view.py); without an answer, everything is shown as measured.
 */
export type CameraView = NonNullable<AnalysisResult["camera_view"]>;
export type Quality = "measured" | "approximate" | "unreadable";

/** Each position, as the upload form and results describe it. */
export const CAMERA_VIEWS: Record<CameraView, { short: string; long: string }> = {
  side_hitting: { short: "Side-on", long: "side-on, from your hitting-arm side" },
  side_toss: { short: "Side-on", long: "side-on, from your tossing-arm side" },
  behind: { short: "Behind you", long: "from behind the baseline" },
  behind_diagonal_hitting: { short: "Back corner", long: "from a back corner, on your hitting-arm side" },
  behind_diagonal_toss: { short: "Back corner", long: "from a back corner, on your tossing-arm side" },
  front: { short: "Across the net", long: "from across the net" },
  front_diagonal_hitting: { short: "Front corner", long: "from a front corner, on your hitting-arm side" },
  front_diagonal_toss: { short: "Front corner", long: "from a front corner, on your tossing-arm side" },
};

const MEASUREMENT_NAMES: Record<string, string> = {
  "trophy.front_knee_flexion": "front knee bend at the trophy position",
  "trophy.back_knee_flexion": "back knee bend at the trophy position",
  "trophy.elbow_angle": "elbow bend at the trophy position",
  "trophy.trunk_tilt": "trunk tilt at the trophy position",
  "racket_drop.elbow_angle": "elbow bend in the racket drop",
  "racket_drop.trunk_tilt": "trunk tilt in the racket drop",
  "contact.elbow_angle": "arm extension at contact",
  "contact.wrist_height": "contact height",
  "contact.front_knee_flexion": "front knee bend at contact",
  "contact.trunk_tilt": "trunk tilt at contact",
};

export function measurementName(phase: PhaseName, metric: MetricName): string {
  return MEASUREMENT_NAMES[`${phase}.${metric}`] ?? `${metric.replace(/_/g, " ")} at ${phase.replace("_", " ")}`;
}

export function qualityOf(result: AnalysisResult, phase: PhaseName, metric: MetricName): Quality | null {
  return (result.quality?.[phase]?.[metric] as Quality | null | undefined) ?? null;
}

/** Every measurement with the given quality, in phase order. */
export function measurementsWith(result: AnalysisResult, quality: Quality): { phase: PhaseName; metric: MetricName }[] {
  const out: { phase: PhaseName; metric: MetricName }[] = [];
  for (const phase of ["trophy", "racket_drop", "contact"] as PhaseName[]) {
    for (const [metric, q] of Object.entries(result.quality?.[phase] ?? {})) {
      if (q === quality) out.push({ phase, metric: metric as MetricName });
    }
  }
  return out;
}

/**
 * The labels with unreadable measurements set to "unknown": their good/borderline/off verdict
 * would be noise, so the skeleton colours and angle labels don't show one.
 */
export function readableLabels(result: AnalysisResult): AnalysisResult["labels"] {
  if (!result.quality) return result.labels;
  const out = structuredClone(result.labels);
  for (const { phase, metric } of measurementsWith(result, "unreadable")) {
    (out[phase] as Record<MetricName, MetricStatus | null>)[metric] = "unknown";
  }
  return out;
}

/** "a", "a and b", "a, b and c". */
export function joinList(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}
