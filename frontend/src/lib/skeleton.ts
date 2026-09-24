import type {
  AnalysisResult,
  FramesPayload,
  Hand,
  LandmarkName,
  MetricName,
  MetricStatus,
  PhaseName,
} from "../api/types";
import type { Point } from "./coords";

export type LandmarkSource = "smoothed" | "raw";

/** Same threshold the pipeline uses to drop low-confidence landmarks. */
export const MIN_VISIBILITY = 0.5;

export const SKELETON_EDGES: [LandmarkName, LandmarkName][] = [
  ["left_shoulder", "right_shoulder"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  ["left_shoulder", "left_hip"],
  ["right_shoulder", "right_hip"],
  ["left_hip", "right_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
];

export type Pose = Partial<Record<LandmarkName, Point>>;

/** Landmarks to draw at one frame; missing or low-visibility points are omitted. */
export function poseAt(
  frames: FramesPayload,
  frame: number,
  source: LandmarkSource,
  minVisibility = MIN_VISIBILITY,
): Pose {
  const pose: Pose = {};
  const tracks = frames.landmarks[source];
  for (const name of Object.keys(tracks) as LandmarkName[]) {
    const track = tracks[name];
    const x = track.x[frame];
    const y = track.y[frame];
    if (x == null || y == null) continue;
    if (source === "raw") {
      const v = frames.landmarks.raw[name].v[frame];
      if (v == null || v < minVisibility) continue;
    }
    pose[name] = { x, y };
  }
  return pose;
}

export interface Sides {
  shoulder: LandmarkName;
  elbow: LandmarkName;
  wrist: LandmarkName;
  frontKnee: LandmarkName;
  backKnee: LandmarkName;
  hip: LandmarkName;
}

/** Hitting side follows the hand; the front leg is on the tossing side. */
export function sidesFor(hand: Hand): Sides {
  const hit = hand;
  const toss = hand === "right" ? "left" : "right";
  return {
    shoulder: `${hit}_shoulder`,
    elbow: `${hit}_elbow`,
    wrist: `${hit}_wrist`,
    frontKnee: `${toss}_knee`,
    backKnee: `${hit}_knee`,
    hip: `${hit}_hip`,
  };
}

/** Which joints each metric is "about", for colouring by status. */
export function metricJoints(hand: Hand): Record<MetricName, LandmarkName[]> {
  const s = sidesFor(hand);
  return {
    elbow_angle: [s.elbow],
    wrist_height: [s.wrist],
    front_knee_flexion: [s.frontKnee],
    back_knee_flexion: [s.backKnee],
    trunk_tilt: ["left_shoulder", "right_shoulder", "left_hip", "right_hip"],
  };
}

/** A status worth marking on the video; "unknown" is drawn as a plain joint. */
export type MarkedStatus = Exclude<MetricStatus, "unknown">;

const SEVERITY: Record<MarkedStatus, number> = { good: 1, borderline: 2, off: 3 };

/** Assessed metric statuses at a phase (stance has none). */
export function metricStatuses(
  labels: AnalysisResult["labels"],
  phase: PhaseName | null,
): Partial<Record<MetricName, MarkedStatus>> {
  const out: Partial<Record<MetricName, MarkedStatus>> = {};
  if (phase === null) return out;
  for (const [metric, status] of Object.entries(labels[phase]) as [MetricName, MetricStatus | null][]) {
    if (status && status !== "unknown") out[metric] = status;
  }
  return out;
}

/** Status per joint at a phase. A joint shared by several metrics shows the worst one. */
export function jointStatuses(
  labels: AnalysisResult["labels"],
  phase: PhaseName | null,
  hand: Hand,
): Partial<Record<LandmarkName, MarkedStatus>> {
  const out: Partial<Record<LandmarkName, MarkedStatus>> = {};
  const joints = metricJoints(hand);
  for (const [metric, status] of Object.entries(metricStatuses(labels, phase)) as [MetricName, MarkedStatus][]) {
    for (const joint of joints[metric]) {
      const existing = out[joint];
      if (!existing || SEVERITY[status] > SEVERITY[existing]) out[joint] = status;
    }
  }
  return out;
}

export interface AngleLabel {
  anchor: LandmarkName;
  metric: MetricName;
  text: string;
}

const LABEL_FORMAT: Record<MetricName, (v: number) => string> = {
  elbow_angle: (v) => `Elbow ${Math.round(v)}°`,
  front_knee_flexion: (v) => `Front knee ${Math.round(v)}°`,
  back_knee_flexion: (v) => `Back knee ${Math.round(v)}°`,
  trunk_tilt: (v) => `Trunk ${Math.round(v)}°`,
  wrist_height: (v) => `Wrist ${v.toFixed(2)}×`,
};

/** On-video angle readouts for one frame, anchored to joints that are visible. */
export function angleLabels(frames: FramesPayload, frame: number, hand: Hand, pose: Pose): AngleLabel[] {
  const s = sidesFor(hand);
  const anchors: Record<MetricName, LandmarkName> = {
    elbow_angle: s.elbow,
    wrist_height: s.wrist,
    front_knee_flexion: s.frontKnee,
    back_knee_flexion: s.backKnee,
    trunk_tilt: s.hip,
  };
  const out: AngleLabel[] = [];
  for (const metric of Object.keys(anchors) as MetricName[]) {
    const value = frames.series[metric][frame];
    const anchor = anchors[metric];
    if (value == null || !pose[anchor]) continue;
    out.push({ anchor, metric, text: LABEL_FORMAT[metric](value) });
  }
  return out;
}
