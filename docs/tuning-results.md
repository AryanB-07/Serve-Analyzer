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
| Trophy fallback (toss-hand peak when knees are missing) | off, on | Recovers the one missed real trophy, but 6 frames off. | Off by default |
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

## Reproducing

```bash
uv run python -m evaluation.real fetch     # download + trim the real clips (not stored in git)
uv run python -m evaluation.real extract   # cache MediaPipe landmarks (~40 s)
uv run python -m evaluation.sweep          # all experiments, about 2 minutes
uv run pytest tests/test_multiview.py      # geometry, handedness and phase-rule tests
```
