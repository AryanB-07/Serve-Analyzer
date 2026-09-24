import { describe, expect, it } from "vitest";

import type { AnalysisResult, FramesPayload, LandmarkName } from "../api/types";
import { angleLabels, jointStatuses, poseAt, sidesFor } from "./skeleton";

const NAMES: LandmarkName[] = [
  "nose", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
  "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
];

function makeFrames(n: number): FramesPayload {
  const raw = Object.fromEntries(
    NAMES.map((name) => [name, { x: Array(n).fill(0.5), y: Array(n).fill(0.5), v: Array(n).fill(0.9) }]),
  ) as FramesPayload["landmarks"]["raw"];
  const smoothed = Object.fromEntries(
    NAMES.map((name) => [name, { x: Array(n).fill(0.4), y: Array(n).fill(0.6) }]),
  ) as FramesPayload["landmarks"]["smoothed"];
  const series = {
    front_knee_flexion: Array(n).fill(40), back_knee_flexion: Array(n).fill(null),
    elbow_angle: Array(n).fill(163.6), trunk_tilt: Array(n).fill(20), wrist_height: Array(n).fill(1.287),
  };
  return {
    fps: 25, n_frames: n, width: 640, height: 480,
    phases: { trophy: 1, racket_drop: null, contact: 2 },
    landmarks: { raw, smoothed }, series,
  };
}

describe("poseAt", () => {
  it("omits missing smoothed points", () => {
    const frames = makeFrames(3);
    frames.landmarks.smoothed.right_wrist.x[1] = null;
    const pose = poseAt(frames, 1, "smoothed");
    expect(pose.right_wrist).toBeUndefined();
    expect(pose.left_wrist).toEqual({ x: 0.4, y: 0.6 });
  });

  it("drops raw points below the visibility threshold", () => {
    const frames = makeFrames(3);
    frames.landmarks.raw.right_elbow.v[0] = 0.2;
    frames.landmarks.raw.left_elbow.v[0] = null;
    const pose = poseAt(frames, 0, "raw");
    expect(pose.right_elbow).toBeUndefined();
    expect(pose.left_elbow).toBeUndefined();
    expect(pose.nose).toEqual({ x: 0.5, y: 0.5 });
  });
});

describe("sidesFor", () => {
  it("puts the front leg on the tossing side", () => {
    expect(sidesFor("right")).toMatchObject({ elbow: "right_elbow", frontKnee: "left_knee", backKnee: "right_knee" });
    expect(sidesFor("left")).toMatchObject({ elbow: "left_elbow", frontKnee: "right_knee", backKnee: "left_knee" });
  });
});

describe("jointStatuses", () => {
  const labels = {
    trophy: { front_knee_flexion: "off", trunk_tilt: "good", elbow_angle: "unknown" },
    racket_drop: {},
    contact: { elbow_angle: "good", wrist_height: "borderline", trunk_tilt: "borderline" },
  } as AnalysisResult["labels"];

  it("colours the joints each metric is about, for the hitting hand", () => {
    expect(jointStatuses(labels, "contact", "right")).toEqual({
      right_elbow: "good", right_wrist: "borderline",
      left_shoulder: "borderline", right_shoulder: "borderline", left_hip: "borderline", right_hip: "borderline",
    });
  });

  it("ignores unknown statuses and uses the front knee for the tossing side", () => {
    const trophy = jointStatuses(labels, "trophy", "left");
    expect(trophy.right_knee).toBe("off");
    expect(trophy.left_elbow).toBeUndefined();
  });

  it("has nothing to show in the stance", () => {
    expect(jointStatuses(labels, null, "right")).toEqual({});
  });
});

describe("angleLabels", () => {
  it("formats values and skips metrics with no value or no visible anchor", () => {
    const frames = makeFrames(3);
    const pose = poseAt(frames, 0, "smoothed");
    delete pose.left_knee;
    const labels = angleLabels(frames, 0, "right", pose);
    expect(labels.map((l) => l.text)).toEqual(["Elbow 164°", "Wrist 1.29×", "Trunk 20°"]);
  });
});
