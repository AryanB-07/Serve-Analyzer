# How well does MediaPipe capture depth?

This doc asks whether the 3D (`world3d`) joint angles are reliable enough to use in place of the
2D image angles. It combines published validation studies with our own tests on 26 real clips.

Run the tests with `python -m evaluation.depth`. The report is in
`evaluation/reports/depth_20260928-201947_d3901c2-dirty.md`.

## What the model says about itself

- MediaPipe fits a GHUM body model to 2D annotations to produce z and the world landmarks.
  The model card calls the result "not metric but up to scale".
- The published accuracy of BlazePose GHUM
  ([Grishchenko et al. 2022](https://arxiv.org/abs/2206.11678)) is:
  - 3D error (MPJPE) of 121 mm;
  - 78 mm after Procrustes alignment, which removes global rotation, scale and position.

  So about a third of the raw error is global pose and scale rather than the shape of the body.
- The model card says the model is out of scope beyond about 4 m. Our filming guide says 5–10 m
  (see "Distance" below).

## What the literature says

| Study | Setup | Finding |
|---|---|---|
| [Lagomarsino et al., BMVC 2024 workshop](https://bmva-archive.org.uk/bmvc/2024/workshops/ANIMA/paper2.pdf) | Vicon ground truth; one camera facing the subject | Close to the gold standard for movements parallel to the image (frontal plane). Significant errors for sagittal-plane (toward-camera) movements, caused by depth estimation and occlusion. |
| [Stereo fusion study, *Sensors* 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11644880/) | Qualisys ground truth; 9 subjects doing squats; frontal and lateral phones | Median RMSE of 56.3 mm from one camera, 30.1 mm with two. The lateral camera beat the frontal one, "due to reduced depth estimation requirements". Knee angle error was 25° on the occluded side against 11° on the visible side. Filtering added nothing, since MediaPipe already smooths internally. |
| [Accuracy evaluation for physical exercises (ResearchGate)](https://www.researchgate.net/publication/374081734_Accuracy_Evaluation_of_3D_Pose_Estimation_with_MediaPipe_Pose_for_Physical_Exercises) | IMU mocap ground truth; several viewpoints | Accuracy "strongly depends on the viewing angle". Error rises under occlusion, and the z-axis "suffers from high noise". |
| [Multi-view camera placement, *BMC Research Notes* 2026](https://link.springer.com/article/10.1186/s13104-026-07886-4) | Multi-camera markerless capture | Two cameras about 45° apart gave an MAE of 9.3° (static) and 12.9° (dynamic). |

The studies agree: monocular depth is the weakest axis, and it gets worse exactly where we need it,
when a limb points at the camera or is hidden behind the body.

## Our tests

These tests need no ground truth. They measure consistency, which is necessary for accuracy but
does not prove it.

### 1. Depth scale, from bone-length constancy

A bone never changes length. If MediaPipe reports depth at s × the truth, the bone's 3D length
varies as it turns toward the camera. We search for the s that makes each bone's length most
constant.

- **Check on synthetic data.** The estimator works on synthetic serves (true → estimated):
  0.3 → 0.50, 0.5 → 0.64, 0.75 → 0.84, 1.0 → 1.06, 1.5 → 1.52. It is biased toward 1 when depth is
  compressed, so real low values are probably even lower.
  - Unit tests in `tests/test_depth.py` also check that it recovers an exact s on noiseless data.
- **Real clips.** Across 133 bones in 26 clips, the median s is **0.98**, with an IQR of
  **0.80–1.28**.
  - By view: front 0.90, front-diagonal 1.04, side-on 1.06, behind-diagonal 1.33 (IQR 0.84–1.72).
  - "Behind" has only 5 usable bones, so treat that view as unmeasured.

On average the depth scale is about right. The spread is large, though: individual bones in
individual clips are off by 20–30% or more, in either direction. The depth errors behave like
noise that depends on the clip, not a steady bias. A steady bias could have been calibrated out;
noise like this cannot.

### 2. Mirror consistency (flipped video)

We ran MediaPipe on each clip flipped left-to-right. A consistent model should return mirrored x
and identical y and depth.

- **Position.** Median disagreement relative to each axis's spread was:
  - x: 0.29
  - y: **0.10**
  - depth: **0.38**

  In absolute terms, depth moved 4.6–7.7 cm per joint.
- **Angles.** The median change in each angle under mirroring, by view:

| View | Knee 2D | Knee 3D | Elbow 2D | Elbow 3D |
|---|---|---|---|---|
| front | 5.8° | 6.3° | 4.9° | 9.9° |
| front-diagonal | 2.3° | 8.5° | 5.9° | **22.0°** |
| side-on | 3.6° | 7.6° | 4.0° | 6.0° |
| behind | 2.0° | 5.8° | 4.1° | 13.1° |
| behind-diagonal | 3.0° | 8.6° | 4.0° | **23.8°** |

This is the most direct result. On the diagonal views, mirroring the same frames changes the 3D
elbow angle by about 22–24°, against 4–6° in 2D. Those diagonal views are the ones `world3d` was
supposed to fix. On side-on, the 3D elbow is almost as stable as 2D. The knee is steadier in 3D
than the elbow, but in 3D it is still worse than 2D on every view except the far front clips.

### 3. Distance (downscaled frames)

We downscaled frames by 2× and 4× to simulate a player further away.

- Detection stayed at about 100% down to a person height of 72–94 px.
- At 4× downscaling, the angles changed by at most 2.6° (knee) and 5.0° (elbow).
- Depth was the axis that moved most, by up to 2.5 cm. The exception was the far front clip, where
  y moved 9.9 cm at 72 px.

Person height in pixels is what matters, not the 4 m figure on the model card. At 1080p, a player
5–10 m away is still roughly 250–500 px tall. So the filming guide can stay, as long as it asks
for the player to fill a reasonable part of the frame.

## Conclusions

1. **Keep `angle_space = "image2d"` as the default.** Real depth is unbiased on average but noisy
   from clip to clip. Under mirroring, 3D elbow angles on the diagonal views change 4–5× more than
   2D angles. So on real footage, `world3d` would swap a known, explainable projection error for
   a larger random one.
   - This agrees with the earlier real cross-view results, which were mixed.
   - It also explains why the synthetic gain (20.2° → 5.4°) only held when depth was recovered at
     75–100%.
2. **3D is usable for knee flexion side-on or near side-on**, where the literature and our numbers
   agree that depth matters least. It is not usable for the elbow on the diagonal views.
3. **Phase timing should stay 2D.** The y axis is by far the most self-consistent (0.10), and the
   phase signals are mostly vertical (wrist height, toss).
4. **Fixing depth properly means a second camera or a different model.**
   - The stereo study halves the error with two phones.
   - Fine-tuning is not an option: Model Maker doesn't support pose, and the training data is
     private.
   - A heavier monocular 3D model (for example MotionBERT, which lifts 2D sequences to 3D) is the
     next thing to try on one camera. It would be a new dependency and would need to meet the
     CPU-time limit, so it needs discussing first.

## Caveats

- Consistency is not accuracy. A model can be confidently and consistently wrong. We have no
  mocap ground truth for tennis serves.
- The estimator is biased toward 1 at low s, so the real compression is probably worse than
  reported.
- The behind view and the far/low-angle front clips have few usable bones or angles.
- The clips come from stock footage and YouTube and are not a controlled sample.
