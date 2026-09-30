# Tuning the pipeline for more camera angles

What was changed, what each setting does to accuracy, and which changes became defaults.
The full numbers are in `evaluation/reports/20260925-185925_54c7b94-dirty.md` (regenerate with
`python -m evaluation.sweep`).

## Method

- **One factor at a time.** Every experiment starts from the original defaults and changes a
  single setting, so any change in the scores is caused by that setting. The winners are then
  combined, to catch interactions.
- **Two ground truths, because neither is enough alone.**
  - *Synthetic* (`evaluation/synthetic.py`): 12 scripted serves (stance, knee depth, left and
    right hand) × 10 virtual cameras (side-on, behind, front, both diagonals, both sides, high).
    Exact 3D truth, run through a detector-noise model calibrated to the real clips. Simulated
    bone-length variation is 5–6% on visible limbs and 15% on occluded ones, against 4–11% and
    11–22% measured on real MediaPipe output. This is the only place metric *accuracy* can be
    measured.
  - *Real* (`evaluation/labels/real_clips.json`): 11 clips across 5 views, 2 players plus the
    fixture, with trophy and contact hand-labelled (about ±1–2 frames), and one clip with no
    complete serve. This measures phase timing on genuine MediaPipe output.
- **Rule for adopting a change:** it must help, or at least not hurt, on **both** synthetic and
  real data, and side-on must not get worse.

## What each setting does

| Setting | Values tried | Effect | Decision |
|---|---|---|---|
| Smoothing window | off, 50–400 ms | 50–150 ms are identical (they round to the same 5-frame window at 25–30 fps). ≥ 250 ms flattens peaks: synthetic contact error 0.4 → 1.1 frames, angle error +2.7°. Turning smoothing off costs 3D angles 0.7° and view spread 1.6°. | Keep **150 ms** |
| Polynomial order | 2, 3 | Identical, as the maths predicts (for a symmetric window, order 2k and 2k+1 give the same smoothing). | Keep 2 |
| Visibility threshold | 0–0.7 | **Real trophy error jumps from 3.6 to 15–32 frames at any value other than 0.5.** Unconfident joints add fake knee and toss signals. No effect on synthetic, because the noise model never hides joints at the scored frames (a known gap in the simulator). | Keep **0.5** for angles |
| Contact visibility threshold (new, separate) | 0–0.3 | Real contact error 0.5 → 0.2 frames; the side-on clip's contact becomes exact (341 → 337). The hitting wrist's *height* survives MediaPipe's low-confidence guesses even when the joint is hidden. | **New default 0.1** |
| Max gap filled | 0–20 frames | ≥ 10 frames: real trophy error 3.6 → 16.3, because filling long gaps invents motion. | Keep 5 |
| Angle space | 2D image, 3D world | 3D: synthetic angle error **20.2° → 5.4°**, spread across views **19.3° → 5.2°**, label accuracy 58% → 88%. Real trophy timing got worse (3.6 → 5.4) until phases were timed from 2D signals (see next row). | Available as `world3d`, **off by default** (see caveats) |
| Phase timing signals | follow angle space, always 2D | With 3D angles, timing phases from 2D restores real trophy error to 3.6. The 2D knee curve times the peak better on real MediaPipe output; 3D measures its size better. | Always 2D (default) |
| Trophy rule | knee + toss arm, toss-hand peak | Toss-hand peak: real error 37 frames. | Keep knee + toss arm |
| Trophy search window | none, 0.6–1.2 s | 0.8 s: real trophy error 3.6 → 2.2, synthetic 1.6 → 1.4. It removes an early knee bend picked 16 frames too soon. 0.6 s scores the same, but 0.8 s leaves margin for slower servers. | **New default 0.8 s** |
| Trophy plateau centre | argmax, 2–6° | Synthetic 1.4 → 1.0, but real 2.2 → 2.7. The sources disagree. | Rejected (option kept) |
| Trophy fallback (toss-hand peak when knees are missing) | off, on | Recovers the one missed real trophy, but 6 frames off. | Off at first; **on since the enlarged retest** (see below) |
| Racket-drop rule | smallest elbow angle, lowest wrist | Lowest wrist: synthetic error 0.9 → 1.5. | Keep smallest elbow angle |
| Complete-serve check | off, on | Rejects the clip that ends mid-toss (it previously reported a phantom contact). No real or synthetic serve lost once contact uses its own threshold. | **New default on** |
| Borderline band width | ×0.5–×2 | Label accuracy 54% → 60%, feedback overlap 0.27 → 0.37. That's an artefact: vaguer bands and longer lists agree more by chance. | No change |
| Feedback points shown | 2–5 | Overlap 0.21 → 0.31, the same artefact. | Keep 4 |

## Results

| | Original | New defaults | New defaults + `world3d` |
|---|---|---|---|
| Synthetic angle error | 20.2° | 20.2° | **5.4°** |
| Same serve, spread across views | 19.3° | 19.4° | **6.2°** |
| Synthetic phase error, trophy / drop / contact (frames) | 1.6 / 0.9 / 0.4 | **1.4 / 0.8 / 0.4** | 1.4 / 0.8 / 0.4 |
| Label accuracy against truth | 58% | 58% | **88%** |
| Real trophy error | 3.6 (1 missed) | **2.2** (1 missed) | 2.2 (1 missed) |
| Real contact error | 0.5 | **0.2** | 0.2 |
| Phantom serve rejected | no | **yes** | yes |
| Side-on angle error (synthetic) | 20.3° | 20.3° | 4.8° |
| Processing after MediaPipe | 20 ms | 20 ms | 38 ms (MediaPipe itself: ~5.7 s) |

## Caveats

1. **The 3D gain depends on one number nobody has measured:** how much depth MediaPipe actually
   recovers. With 3D angles, synthetic error is 5.4° if it recovers 75–100% of depth, 9.1° at
   50–75%, 14.1° at 25–50%, and 18.5° at 0–25%, still no worse than 2D's 20.2°. On the real clips:
   - **From behind, the Pexels player's 3D knee reading (33°) is almost the same as 2D (29°).**
     That suggests depth recovery is weak along the camera's line of sight.
   - 3D made the *same-view* readings much steadier across four serves (knee spread 5.8° →
     1.9°, elbow at contact 17.5° → 5.6°).
   - **Across views the real result is mixed:** front-knee spread went 42° → 32°, but back-knee
     39° → 54°. Those are different serves, so this doesn't prove anything either way.

   **Simultaneous multi-view recordings are the only way to settle it**, which is why `world3d`
   isn't the default yet.
2. **Only 10 real serves, labelled by eye.** The trophy-window and contact-threshold values could
   be partly fitted to these clips. Both rules are generic (a time window, one visibility value),
   and synthetic data agrees for the window, but they should be re-checked on new footage.
3. **Elbow at contact gets slightly worse in 3D** (4.2° → 6.6° synthetic), where 2D was already
   good. A per-metric choice of 2D or 3D could fix that, but it would be tuning on synthetic data
   alone.
4. **The simulator's visibility model is simplified.** It can't evaluate the visibility threshold;
   only the real clips can.

## Retest on a larger real set

The real set was enlarged from 10 serves (3 players) to 24 serves (5 players), plus a second clip
with no complete serve: 10 serves and a trophy-position demonstration from a coaching video on clay
and in a dark studio (one serve is a slow-motion replay), two clips from a published study filmed
across the net, and two more Pexels clips (one filmed from below with the legs cut off, one through
a fence). Labels were made the same way (by eye, about ±1–2 frames); the detected contact agrees
with them within 0–3 frames on every new clip.

Every combination of the phase and cleaning settings was then scored: 96,000 configurations
(visibility 0.3–0.5, contact visibility 0–0.3, smoothing off/100–250 ms, gap 0–8 frames, trophy
window 0.5–1.2 s or none, plateau off/1–4°, fallback off/on, both racket-drop rules), on the real
clips and on synthetic serves with fresh noise seeds.

**The search does not generalise, so the defaults stay, with one exception.**

- Choosing the best configuration without one player and scoring it on that player is slightly
  *worse* than the defaults on average (3.80 vs 3.68).
- No configuration beats the defaults clip by clip by more than chance (best one-sided sign test
  p = 0.12). The in-sample "best" combination (smoothing off, 0.6 s window, 4° plateau, fallback,
  lowest-wrist racket drop) wins on 10 clips and loses on 6.
- **Trophy fallback is now on.** It can only change a clip whose trophy would otherwise be missing,
  so it can't make any clip worse; it recovered both such clips (legs out of frame), each 6 frames
  early, and it lets racket drop be detected there too. Every held-out selection picked it.

Settings that looked promising but were not adopted:

| Setting | Why not |
|---|---|
| Smoothing off | 8 clips better, 4 worse (p = 0.19). Most of the gain is one clip; worse for the player with the most clips. |
| Shorter trophy window (0.5–0.6 s) | Helps fast serves but cuts off slower ones. Synthetic serves all share one tempo, so they can't judge it. |
| Longer trophy window (0.9 s or more) | Fixes the slow-motion clip but picks an early knee bend on an old clip at 1.0 s and above. |
| Plateau centre | Worse on real clips at every value (e.g. 3 better, 8 worse at 3°). |
| Visibility, contact visibility, gap | At most one clip changes by a frame. |

Failure modes no setting can fix:

- **Left/right swaps.** On the trophy-position demonstration (front view), MediaPipe swaps the
  wrists partway through, so the raised toss arm is read as the hitting arm and the clip is accepted
  as a serve.
- **Slow-motion footage.** The trophy window is in seconds of video, so on a slow-motion replay the
  trophy is found 10 frames late. Scaling the window by the serve's measured tempo would fix this
  better than any fixed value.

Remaining caveat: 24 serves is still small, and 11 of them come from one person.

## Round 3: model size, label swaps, slow motion, rebuilt depth

Four more experiments, each tested against the current defaults on all 26 real clips. The full
numbers are in `evaluation/reports/20260929-155450_eb990b5-dirty.md` and
`evaluation/reports/depth_20260929-155148_eb990b5-dirty.md`.

| Experiment | Result | Decision |
|---|---|---|
| **Pose model size** (lite / full / heavy) | 6.5 / 7.4 / 15.4 ms per frame on CPU. Lite and full both lose the behind-view clip (trophy and contact 64 frames early). Real trophy error is 5.4 / 5.2 / 3.0 frames; contact error is 3.6 / 3.3 / 0.46. | Keep **heavy** |
| **Left/right swap repair.** A two-state Viterbi relabels frames where MediaPipe flips the whole body's left/right labels, choosing the most continuous path with a penalty for each switch. | With continuity measured on all joints, penalties of 0.1–0.5 "repair" genuinely fast arm swings near contact: contact error 0.46 → 0.7–5.5 frames, and up to 2 serves lost. Penalty 1.0 never fires. Measuring continuity on torso, hips or legs only didn't help either. The trophy-demo clip it targets has MediaPipe's *majority* labelling inverted, so continuity can't fix it, and no orientation cue is reliable: face visibility reads 1.00 even from behind. | **Rejected**, code removed |
| **Slow-swing trophy window** (`trophy_window_min_swing_speed`). The trophy window is stretched by threshold ÷ speed when the hitting wrist's peak speed is below the threshold (in torso lengths/s). | Real serves measure 11–32 and the slow-motion replay 6.4. At 10, that clip's trophy error goes 10 → 0 frames and no other clip changes (real mean 3.0 → 2.6). At 13 and above it overshoots. Synthetic trophy error rises 1.4 → 1.6 frames, because the synthetic serves swing at 6.5–10 torso lengths/s, slower than any real serve. | **Optional, off by default.** It rests on one clip, and the simulator's tempo is unrealistic, so the simulator can't judge it. Turn it on at 10 once more slow-motion footage confirms it. |
| **Depth rebuilt from bone lengths** (`angle_space="bone3d"`). Keeps MediaPipe's x and y; each limb bone's depth is √(L² − xy²), where L is the 85th percentile of the bone's x-y length; the sign of the depth comes from MediaPipe. | Synthetic data: it degrades much more slowly than world3d as depth is compressed (6.5 / 6.9 / 7.5 / 10.2° against 5.4 / 9.1 / 14.1 / 18.5°). The 80th–85th percentiles beat 90–99, because noise inflates the top of the range. Real mirror test: *less* consistent than world3d on every view (diagonal elbow 24–30° against 22–24°; 2D is 4–6°). Rebuilding magnifies x/y noise when a bone lies nearly flat to the image, and a wrong depth sign doubles the error. | Kept as an experimental option; **2D stays the default** |

Smoothing depth more heavily (300–800 ms, depth only) doesn't change the mirror-test numbers. The
depth disagreement is systematic from frame to frame, not jitter, so filtering can't fix it. This
supports the conclusion in `docs/mediapipe-depth.md`: dependable 3D needs a second camera or a
different model.

The sweep's "phantom rejected" figure now counts both no-serve clips; it had reported only the
last one. The original defaults reject 0 of 2 and the current defaults reject 1 of 2. The
trophy-position demo, a real motion that isn't a serve, still gets through.

## Reproducing

```bash
uv run python -m evaluation.real fetch     # download + trim the real clips (not stored in git)
uv run python -m evaluation.real extract   # cache MediaPipe landmarks (~40 s)
uv run python -m evaluation.sweep          # all experiments, about 2 minutes
uv run pytest tests/test_multiview.py      # geometry, handedness and phase-rule tests
```
