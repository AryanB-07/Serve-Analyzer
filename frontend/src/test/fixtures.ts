import type { AnalysisResult } from "../api/types";

/** A trimmed-down AnalysisResult shaped like the demo fixture. */
export function makeResult(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  const none = { front_knee_flexion: null, back_knee_flexion: null, elbow_angle: null, trunk_tilt: null, wrist_height: null };
  return {
    id: "test",
    hand: "right",
    fps: 25,
    n_frames: 125,
    width: 640,
    height: 480,
    phases: { trophy: 113, racket_drop: null, contact: 124 },
    metrics: {
      trophy: { ...none, front_knee_flexion: 86.2, trunk_tilt: 20.2 },
      racket_drop: { ...none },
      contact: { ...none, front_knee_flexion: 4, trunk_tilt: 20, wrist_height: 1.287 },
    },
    labels: {
      trophy: { front_knee_flexion: "borderline", back_knee_flexion: "unknown", elbow_angle: "unknown", trunk_tilt: "good" },
      racket_drop: { elbow_angle: "unknown", trunk_tilt: "unknown" },
      contact: { elbow_angle: "unknown", wrist_height: "borderline", front_knee_flexion: "good", trunk_tilt: "good" },
    },
    ranges: {
      trophy: {
        front_knee_flexion: { good: [50, 80], borderline: [35, 95] },
        back_knee_flexion: { good: [45, 80], borderline: [30, 95] },
        elbow_angle: { good: [80, 120], borderline: [65, 140] },
        trunk_tilt: { good: [15, 35], borderline: [8, 45] },
      },
      racket_drop: {
        elbow_angle: { good: [50, 90], borderline: [35, 110] },
        trunk_tilt: { good: [10, 30], borderline: [5, 40] },
      },
      contact: {
        elbow_angle: { good: [160, 180], borderline: [145, 180] },
        wrist_height: { good: [1.3, 1.6], borderline: [1.15, 1.7] },
        front_knee_flexion: { good: [0, 20], borderline: [0, 35] },
        trunk_tilt: { good: [5, 30], borderline: [0, 40] },
      },
    },
    feedback: [
      {
        text: "Hit the ball higher: at contact your wrist is at 1.29 body heights (target 1.30-1.60).",
        phase: "contact",
        metric: "wrist_height",
        status: "borderline",
      },
      {
        text: "You sit very deep on your front knee at the trophy (86°, target 50-80°).",
        phase: "trophy",
        metric: "front_knee_flexion",
        status: "borderline",
      },
    ],
    warnings: [],
    video_url: "/mock/test/playback.mp4",
    annotated_video_url: null,
    thumbnail_url: null,
    ...overrides,
  };
}
