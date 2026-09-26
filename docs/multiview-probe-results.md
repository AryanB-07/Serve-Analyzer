# How the current pipeline copes with different camera angles

Exploratory tests of the **current** pipeline (2D image angles, heuristic phases). They were
run before any multi-view work, as an informal baseline for `docs/multiview-research.md`. These
are **not** the formal milestone-2 evaluation: there are no simultaneous multi-view recordings
yet, and the labels were marked by eye from frame grids (about ±1–2 frames).

## 1. Synthetic: one exact serve, many virtual cameras

A scripted 3D right-handed serve with known angles (knee 62° at trophy, elbow 100° at trophy,
50° at racket drop, 172° at contact) and known phase frames. It was projected through a pinhole
camera placed around the player and run through the current pipeline with a perfect detector
(every landmark visible).

**Phase detection held up: ±1 frame from every view.** The *timing* of the knee and wrist
peaks survives projection even when their *size* doesn't.

**Metrics did not.** Values at the true phase frames:

| View | Front knee @ trophy (true 62) | Elbow @ trophy (true 100) | Elbow @ racket drop (true 50) | Trunk tilt @ trophy (true 22) | Elbow @ contact (true 172) | Wrist height @ contact (true 1.24) |
|---|---|---|---|---|---|---|
| Side-on (right sideline) | 47 | 151 | 56 | 21 | 168 | 1.25 |
| Side-on (left sideline) | 44 | 173 | 75 | 21 | 168 | 1.22 |
| Front-diagonal 45° | **1** | **28** | **3** | 19 | 173 | 1.23 |
| Behind the baseline | 45 | 72 | 33 | **6** | 178 | 1.24 |
| Side-on, camera 2 m high | 49 | 174 | 74 | 21 | 168 | 1.22 |
| **Spread across 8 views** | **58** | **146** | **73** | 16 | 10 | 0.04 |

Which view "sees" knee bend depends on the player's stance: 2D front-knee flexion at trophy for
the same true 62°:

| Knees point toward | Side-on | Behind | Front-diagonal |
|---|---|---|---|
| The net | 61 | 0 | 47 |
| 45° (typical) | 47 | 45 | 1 |
| The sideline | 1 | 61 | 46 |

Elbow at contact and wrist height are nearly view-proof. Knee, elbow before contact and trunk
tilt are not, and even the side view isn't accurate, because joints don't move in a single
plane.

## 2. Real footage: 11 serves, 5 views, full pipeline including MediaPipe

The clips are Creative Commons (Wikimedia) and Pexels-licence videos, **not committed**. One
player was filmed from five angles on Pexels, in different serves, not simultaneously. A second
player hit four serves from the same behind-diagonal view (Wikimedia). The fixture clip is a
third, front view.

### Phase detection against hand labels (detected − true, in frames; 1 frame = 33–40 ms)

| Clip | View | Trophy | Contact |
|---|---|---|---|
| fixture | front | +1 | 0 |
| pexels | front (close) | **missed** | 0 |
| pexels | front (far) | −4 | 0 |
| pexels | front-diagonal | 0 | +1 |
| red jacket ×4 | behind-diagonal | +4, **−16**, −3, +2 | 0, 0, 0, 0 |
| pexels | side-on | +1 | +4 |
| pexels | behind | +1 | 0 |
| pexels | side-on, low camera | — | **phantom** |

- **Contact is robust:** 9 of 10 within ±1 frame, across every view.
- **Trophy is the weak phase:** 5 of 10 within ±2 frames, one missed, worst −16 (from behind).
- **The low-camera clip ends mid-toss, yet the pipeline reported a contact at frame 171**, while
  the player was bouncing the ball. There was no warning. It needs a "no complete serve found"
  check.

### Metrics at the hand-labelled frames

| | Front knee @ trophy | Back knee @ trophy | Elbow @ trophy | Trunk tilt @ trophy | Elbow @ contact | Wrist height @ contact |
|---|---|---|---|---|---|---|
| Same player, **5 views**: spread | **41°** | **53°** | **55°** | **20°** | **84°** | 0.08 |
| Same player, **same view, 4 serves**: spread | 7° | 7° | 98°* | 6° | 18° | 0.03 |

\* Elbow at trophy is unstable even within one view: the hitting arm is barely visible from
behind (see below).

Cross-view spread is 5–10× the serve-to-serve spread for knees and trunk. The Pexels serves are
different serves, so part of their spread is real variation, but it can't explain a 41–53°
spread when the same-view noise floor is about 7°.

### MediaPipe visibility of the hitting arm (median visibility score)

| View | Right wrist | Right elbow |
|---|---|---|
| Front / front-diagonal | 0.90–1.00 | 0.79–1.00 |
| Behind | 0.66 | 0.62 |
| Behind-diagonal | 0.28–0.41 | 0.09–0.19 |
| **Side-on (hitting arm on the far side)** | **0.23** | **0.05** |

With the 0.5 visibility threshold, **the elbow metrics vanish in the side-on clip**: the camera
was on the non-hitting side, so the hitting arm was behind the body. Even the one view the
pipeline was designed for works only from the hitting-arm side.

### Speed

About 15 ms per frame for pose extraction at every resolution tested (320×240 to 1920×1080);
MediaPipe resizes internally.

## 3. What this changes in the plan

1. **Phase detection:** keep contact as it is. Trophy is the phase to fix: its knee signal is
   too flat from behind.
2. **Metrics are the main problem,** as predicted: knee, elbow before contact, and trunk tilt.
3. **New requirement:** handle a hitting arm on the far side of the body (side-on from the
   wrong side, and behind-diagonal). 3D world landmarks estimate occluded joints, but noisily,
   so they need a confidence signal rather than silent values.
4. **New requirement:** refuse clips with no complete serve, instead of reporting a phantom
   contact.
