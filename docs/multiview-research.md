# Multi-view analysis: audit, research note and plan

Status: proposal, awaiting approval. No pipeline code has changed.

## 1. How the pipeline works today

| Stage | Where | What it does |
|---|---|---|
| Pose extraction | `serve_analyzer/pose.py:47-83` | MediaPipe `PoseLandmarker` (heavy, VIDEO mode, CPU). Keeps only the **normalised image landmarks** (x, y, visibility), converted to pixels. MediaPipe also returns `z` and hip-centred **world landmarks** (x, y, z in metres); both are thrown away. |
| Cleaning and smoothing | `preprocessing.py` | Points with visibility below 0.5 become NaN; interior gaps of 5 frames or fewer are filled linearly; a Savitzky–Golay filter (150 ms, order 2) runs on each continuous stretch. It works on x and y independently and doesn't depend on the view. |
| Angles | `angles.py:25-90` | Every angle is **2D, in the image plane**: knee flexion = 180° − angle(hip, knee, ankle); elbow = angle(shoulder, elbow, wrist); trunk tilt = angle of the mid-hip→mid-shoulder line from **image vertical**; wrist height = (lower ankle y − wrist y) / (nose-to-ankle distance). |
| Phase detection | `phases.py:25-64` | Contact = the frame where the hitting wrist is highest in the image. Trophy = the deepest **2D** knee flexion before contact while the toss wrist is above the toss shoulder. Racket drop = the smallest **2D** elbow angle between the two. |
| Reference comparison | `reference.py`, `data/reference_ranges.json` | One set of good/borderline ranges per phase and metric, with no notion of camera view. Labels feed the ranked feedback rules in `feedback.py`. |

## 2. Where the side-view assumption is baked in

| # | Location | Assumption | What breaks from behind or at 45° |
|---|---|---|---|
| 1 | `pose.py:70,82` | Only 2D image landmarks are kept | All depth information is discarded before any angle is computed. |
| 2 | `angles.py:25-37` (`joint_angle`) | The joint bends in a plane parallel to the image | Foreshortening. A 90° knee measures 69° at 45° and **0° from directly behind** (§3.1). The elbow has the same problem. |
| 3 | `angles.py:79-80` (`knee_flexion`) | Knee flexion is visible in the image plane | From behind, the knees bend toward the camera, so every serve looks straight-legged. |
| 4 | `angles.py:40-44, 86` (`tilt_from_vertical`) | Trunk tilt means the sagittal lean you see from the side | From behind, the same number measures *sideways* lean (shoulder-over-shoulder tilt), a different movement. It's unsigned, so the two can't be told apart. |
| 5 | `angles.py:65-66` | Averaging left and right shoulder/hip is safe because they overlap from the side | From behind or at 45° the two sides are far apart, so the average changes meaning with the view. |
| 6 | `angles.py:68-77` | "Lower ankle" and height use image y as world vertical | This only holds for a level camera. A high camera squashes heights, and nothing detects it. |
| 7 | `phases.py:36-38` (`detect_trophy`) | Trophy = peak 2D knee flexion | Behind the baseline the knee signal is nearly flat, so the argmax is noise and trophy is detected at the wrong frame. |
| 8 | `phases.py:47-48` (`detect_racket_drop`) | Minimum 2D elbow angle | From behind, the forearm points at the camera during the drop, so the 2D angle is foreshortened. |
| 9 | `phases.py:25-27` (`detect_contact`) | Highest wrist in the image | **Mostly view-invariant** for a level camera; the vertical axis survives all three target views. Keep it. |
| 10 | `data/reference_ranges.json` | One range per metric | The ranges are side-view 2D numbers. Even with correct metrics they would need re-deriving per metric definition. |
| 11 | `landmarks.py:3, 64-76` | MediaPipe left/right are anatomical; the front leg is on the tossing side | Anatomical left/right is right in principle, but MediaPipe must *infer* which way the person faces, and it can flip left and right when the player faces away. (The fixture clip already confused me once in phase 1.) Handedness and view have to be resolved together. |
| 12 | `config.py:17` (visibility 0.5) | The far side is occluded, the near side is visible | From behind, the torso hides the hands at trophy, so the *hitting* arm is dropped instead of the far one. |
| 13 | `feedback.py:30, 53` | Copy says "check the camera is level and side-on" and talks about shoulder tilt | The advice text assumes a side view. |
| 14 | Frontend `FilmingGuide.tsx:5`, `CameraDiagram.tsx` | The filming guide shows side-on only | Needs all supported views. |

## 3. Evidence gathered for this note

### 3.1 How badly 2D angles distort by view (synthetic, exact)

A leg with a true 90° knee bend, projected through a pinhole camera orbiting the player 8 m away:

| Camera | 2D knee flexion |
|---|---|
| Side-on | 90.0° |
| Oblique 30° | 80.7° |
| Oblique 45° | 69.1° |
| Oblique 60° | 51.7° |
| Nearly behind (80°) | 19.0° |
| Behind (90°) | 0.0° |
| Side-on, camera 25° high | 95.6° |

2D angles aren't just noisy off-axis; they are **systematically wrong**. No per-view reference ranges can fix a metric that reads 0° for every serve.

### 3.2 How noisy MediaPipe world landmarks are (the fixture clip, a front view, 125 frames)

| Measure | 3D world landmarks | 2D image landmarks |
|---|---|---|
| Bone-length variation, well-tracked limbs (CV) | 4–11% | 10–25% |
| Shoulder / hip width variation (CV) | 7% | 59–69% (changes with body rotation) |
| Frame-to-frame knee-angle jitter | 2.3–2.5° | 3.5–4.2° |
| Positional jitter (median second difference) | x 5 mm, y 3 mm, **z 5 mm** | — |
| Occluded limbs, bone-length CV | 11–22% | 19–26% |
| Extra cost | None; the same inference call returns them | — |

Takeaways: world depth is no noisier than x in this clip; 3D bone lengths are 2–3× steadier than 2D; occluded limbs stay noisy in 3D. Hip width comes out at 0.14 m, so MediaPipe's skeleton has its own proportions: use **angles and ratios**, never raw metre distances. This is **one clip from one view**; the real per-view noise is exactly what the evaluation in §6 will measure.

### 3.3 External resources checked

- **VideoPose3D:** CC BY-NC (non-commercial), PyTorch, Human3.6M 17-joint format.
- **MotionBERT:** code Apache-2.0; checkpoints 61 MB (Lite) and 162 MB. The released weights are trained on Human3.6M, whose licence is research and non-commercial. It needs PyTorch or an ONNX export, plus a MediaPipe-33 → H36M-17 joint mapping. I haven't benchmarked its CPU speed; it would have to be measured.
- **THETIS** (tennis, Kinect, 55 players, includes serves): the "3D skeletons" are **rendered `.avi` videos, not joint coordinates**, the repo has no licence, and it's single-view. Not usable as 3D ground truth.
- **CMU MoCap** (free for any use): I couldn't confirm any tennis-serve trials.
- I found **no public multi-view tennis-serve dataset**. The evaluation data has to be recorded.

## 4. Approaches compared

| | Accuracy across views | Complexity | CPU cost | Data needed | Dependencies / licence | Verdict |
|---|---|---|---|---|---|---|
| **A. View classification + per-view logic** | Only as good as the per-view 2D metrics, which §3.1 shows are unfixable from behind. Useful as a *detector*. | Low | ~0 | A handful of labelled clips per view for thresholds | None | **Use as a gate**, not a metric strategy: view label, confidence, "unsupported view" messages. |
| **B. MediaPipe world landmarks, 3D angles** | Large improvement expected; measured noise is moderate (§3.2). Weakest on occluded limbs. | Low | ~0 (already computed) | Real multi-view clips to *measure*; none to train | None | **Core of the plan.** |
| **C. 2D→3D lifting (VideoPose3D / MotionBERT)** | Probably the best temporal consistency, but trained on Human3.6M poses (no serves), so domain shift on a serve is unknown. | High: joint remapping, window handling, a new runtime | Unmeasured; likely within 2× with ONNX, not certain | None to train | PyTorch or onnxruntime; weights licensed for research only | **Defer.** Revisit only if B misses the consistency target, as a separately approved experiment. |
| **D. Body-centric normalisation** | In 2D alone it only removes translation, scale and in-plane rotation; it **cannot undo out-of-plane view change**. With 3D (B) it makes every feature relative to the body. | Low–medium | ~0 | None | None | **Combine with B**: a body frame from the 3D hip axis and spine. |
| **E. Learned phase classifier + synthetic multi-view** | Could beat heuristics, but only if trained on enough *labelled* serves; synthetic reprojection of 3D sequences gives view diversity for free. | Medium–high | Tiny GRU/1D-CNN, < 50 ms | Labelled phase frames (we have none) plus 3D sequences to rotate | Training framework (PyTorch dev-only, or NumPy by hand); inference can be pure NumPy | **Build the augmentation and tests; ship only if it beats the heuristic** on held-out real clips. |

## 5. Recommendation

1. **Metrics: B + D.** Store world landmarks, build a per-frame body frame (origin mid-hip; x = hip axis; y = world up; z = forward), and compute every angle in 3D. Wrist height becomes a body-relative ratio in 3D.
2. **View: A as a gate.** Estimate the camera's view angle from the body frame's orientation relative to the camera, which world landmarks give directly, and camera pitch from the upright stance. Output `view` (side / behind / front-oblique / unsupported), `view_confidence` and a specific message when a clip can't be trusted ("filmed from too high an angle — try filming at hip height").
3. **Phases: heuristics rebuilt on view-invariant 3D features** first (contact stays vertical; trophy from 3D knee flexion and toss-arm elevation; racket drop from 3D elbow angle). Then **E as a challenger**, promoted only if it wins on held-out real labels.
4. **Handedness × view:** resolve MediaPipe left/right flips using the body frame (facing direction versus the toss/hitting arm), with synthetic mirrored tests.
5. **Reference ranges:** re-derive for 3D metric definitions; keep the ranges view-independent, because making the *metric* invariant is the point. If a metric still differs by view after this, the eval will show it and we add per-view ranges for that metric only.
6. **Flags** in `AnalysisConfig`: `angle_space: "image2d" | "world3d"`, `view_gate: bool`, `phase_detector: "heuristic2d" | "heuristic3d" | "learned"`. The eval report runs every combination side by side. The default stays today's behaviour until the numbers justify switching.

## 6. Evaluation design

**Dataset layout** (`evaluation/dataset/`, videos git-ignored; manifest and labels committed):

```
evaluation/dataset/
  manifest.json          # clips, groups, view, hand, fps, sync offsets
  labels/<clip_id>.json  # hand-marked trophy / racket_drop / contact frames
  videos/<group_id>/<clip_id>.mp4
```

- A **group** is one serve filmed at the same time by 2–3 phones.
- **Sync:** one hand-marked contact frame per clip sets the offset within its group (the default, no dependencies). Audio sync on the ball strike is optional: it needs an audio decoder (`imageio-ffmpeg`, a ~30 MB binary), to be agreed first.
- **Labelling tool:** a small OpenCV window (already a dependency) to step through frames and mark phases, writing the label JSON.

**Metrics:**
- Phase accuracy per view: mean absolute error in frames and ms, and the fraction within ±2 and ±5 frames.
- **View consistency** (the key number): for each group, each metric and each phase, the spread (max − min and std) across views. It's computed twice: at the *labelled* phase frames, which isolates metric error, and at the *detected* frames, which is end to end.
- View-classification accuracy.
- Seconds per clip.

**Report:** `python -m evaluation.report --config <flags>` writes `evaluation/reports/<timestamp>_<commit>.{json,md}`, with a per-view table and deltas against a chosen baseline report.

**Synthetic benchmark** (runs without any video): 3D pose sequences (world landmarks from real clips) rotated to virtual cameras and reprojected to 2D. It gives exact ground truth for the geometry and is the training source for E. It can't show MediaPipe's own per-view errors; only real clips can.

## 7. Data you would need to record

- **8 serve groups minimum** for a first signal, 15–20 for trustworthy numbers. Each group: three phones recording at the same time (side-on, behind the baseline, front-diagonal ~45°), at hip height, 5–10 m away, 60 fps if possible.
- Clap once in view before serving, to make sync and labelling easier.
- Include **at least 2–3 left-handed groups**, or a left-handed teammate; the handedness × view tests need real ones too.
- Without this data, only the synthetic benchmark and the single fixture clip can produce numbers, and "no change merged without numbers" would mean *synthetic* numbers only.
