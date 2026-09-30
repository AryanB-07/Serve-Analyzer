# Rejecting clips that aren't a serve

The analysis only makes sense for a serve. If someone uploads a forehand, a backhand or a
clip of something else, it should fail with a clear reason rather than report numbers. That
failure is the `NOT_A_SERVE` error.

Reproduce the numbers below with:

```bash
uv run python -m evaluation.negatives fetch   # the non-serve videos
uv run python -m evaluation.negatives         # writes evaluation/reports/serve_check_<time>.md
```

The current report is `evaluation/reports/serve_check_20260929-224033_eb990b5-dirty.md`.

## What counts as a serve

A serve is a ball toss that rises and peaks first, then a swing that reaches well above the head
while the tossing arm comes down. `phases.serve_rejection` checks each part, in torso lengths so
the checks don't depend on distance, and returns the first one that fails:

| Check | Threshold | Weakest real serve | Typical failure |
|---|---|---|---|
| The hitting wrist is above the nose at contact | ≥ 0.3 torso lengths | 0.43 | Forehands, slices, two-handed backhands |
| The toss hand is below the hitting wrist at contact | ≥ 0.5 | 1.09 | Basketball shot, jumping jacks |
| The toss hand peaks before contact | ≥ 0.2 s | 0.30 s | Arms swinging up together; the trophy-position demo |
| The toss hand climbs up to that peak | ≥ 0.9 | 1.26 | Holding the racket instead of tossing |

The checks run after the existing rule: some toss before contact, and the hitting wrist above
the nose at contact.

**How the thresholds were chosen.** Each is about 70% of the weakest value among the 24
labelled real serves. The thresholds were therefore set from serves alone, not tuned to reject
the non-serve clips, and every real serve clears each one comfortably. I did look at the
non-serve clips when choosing *which* features to check, which is why the held-out test below
matters.

**Hidden joints pass.** If the toss hand isn't visible at contact, that check is skipped, so an
occluded toss arm can't reject a real serve. The toss peak is found in the last 1.5 s before
contact, and its climb is measured from the start of the clip. That way a slow-motion toss,
which starts several seconds of video before contact, still counts.

## Results

Each non-serve video is cut into 4-second windows, each standing for one upload. A window counts
as wrongly accepted if either hand setting accepts it.

| | Before | Now |
|---|---|---|
| Backhands, including slice | 6/11 accepted | **2/11** |
| Forehands | 1/5 | **0/5** |
| Volleys, drop shots, lobs | 0/8 | 0/8 |
| Smashes | 3/4 | 3/4 |
| Other sports (basketball, pitching, javelin, volleyball serve) | 1/9 | **0/9** |
| Exercise (squats, jumping jacks, burpees) | 4/20 | **0/20** |
| **All non-serve windows** | **15/57 accepted** | **5/57** |
| Real serves kept | 24/24 | 24/24 |
| Synthetic serves kept (12 serves × 10 cameras) | 120/120 | 120/120 |
| Real clips with no complete serve, rejected | 1/2 | **2/2** |
| Synthetic toss without a swing, rejected | 120/120 | 120/120 |

**Held-out test.** Four videos (a volleyball serve, two jumping-jack videos, and squats with a
front raise) were downloaded only after the thresholds were fixed. The old check accepted 4 of
their 21 windows, all jumping jacks; the new check accepts none.

## What still gets through, and why

- **Smashes (3 of 4 windows).** A smash is an overhead swing whose free arm rises to track the
  ball, which from the body alone looks like a toss. The one real difference is the ball toss
  itself: in a smash the ball comes from the other side of the court. That needs ball tracking.
- **One-handed backhands with a high finish (2 of 11).** This player's follow-through ends with
  the racket arm straight above the head and the other arm down and back, the same shape as a
  serve at contact.

## Limits

- **"Missed" serves.** A toss the player catches without swinging is rejected (the synthetic
  toss-without-swing case). A full swing that misses the ball can't be detected from pose: the
  body moves exactly as in a serve, and the pipeline doesn't track the ball or racket.
- **This isn't a trained model.** The data can't support one. With 24 serves from about six
  players and 57 non-serve windows from 16 videos, a classifier would learn these particular
  players and cameras. The checks are few, physically meaningful, and set from the serves, so
  they have little room to overfit.
  - The data a learned classifier would need: a few hundred labelled clips, including smashes
    and backhands from several players and angles.
  - A cheap way to collect it: a "this isn't a serve" button on the results page, plus the
    `NOT_A_SERVE` failures users dispute.
- **All the non-serve tennis strokes come from one player and one camera.** Other players'
  strokes may behave differently.
