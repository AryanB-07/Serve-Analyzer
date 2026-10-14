# Telling the camera view from the landmarks

Tier 1 of the multi-view plan: work out where the camera was from the skeleton alone, then
report only what that view can measure. **It didn't meet its targets, so it isn't in the app.**
This page records what was tried, the numbers, and why, so the next attempt starts from the
evidence.

Reproduce it with `python -m evaluation.views`. The report is
`evaluation/reports/views_20261014-160401_3d68dba-dirty.md`.

## The method

The line from the tossing shoulder to the hitting shoulder (and the same for the hips) gives the
camera's angle around the **body** (`serve_analyzer/view.py`):
- how long the line looks across the picture;
- which end MediaPipe puts nearer the camera.

Subtracting how far servers are turned at the set position, just before the toss, gives the
angle around the **court**. That angle is binned into five views (behind, behind-diagonal,
side-on, front-diagonal, front), plus the side (hitting or tossing arm). It takes 0.04 ms a
clip.

## Results

| | Side-on detection | Side | Category |
|---|---|---|---|
| **Target** | 95% | 95% | 85% |
| Synthetic rig, every player stands at 80° (the rig's default) | 100% | 100% | 100% |
| Synthetic rig, stance varied like the real players (−20° to 90°) | 62% | 66% | 44% |
| **Real clips:** set position, stance turn fitted leaving each player out | 73% | 62% | 42% |
| Real clips: trophy position | 58% | 54% | 8% |
| Real clips: contact | 77% | 69% | 42% |

**The 100% is circular.** The rig makes every player stand the same way, so subtracting that
turn is exact. Once the stance varies like the real players', the synthetic accuracy collapses to
the same level as the real clips.

The body angle itself is accurate: within 2.6° (median) on the rig. The failure is in turning a
body angle into a court angle.

## Why it can't work from the skeleton alone

1. **Players stand differently.** The turn each real clip implies at the set position, if its
   label is right:
   - the indoor player stands fully side-on, at +88° to +90°;
   - the Pexels player stands anywhere from −29° to +38°;
   - the coach squarely faces the net in the studio clips, at about −10°.

   That's a 90° spread between players, against 45° categories. The skeleton shows how the body
   is turned relative to the camera, not where the net is, so nothing in it separates "front
   camera, sideways player" from "side camera, player facing the net".
2. **MediaPipe swaps left and right in profile.** In the coach's side-on clips (`evd_clay_1` and
   `evd_clay_3`), the follow-through shows the camera on the hitting side. Yet MediaPipe labels
   the raised toss arm "right" at the trophy, and its "right" wrist has 0.2–0.4 visibility. The
   estimate comes out exactly 180° wrong (implied turns of ±175°).

   Every cue that needs to know which shoulder is the hitting one inherits these swaps: the
   depth sign, the left-to-right order, the arm's visibility. Side-on, where the side matters
   most, is where they happen. (Repairing the swaps by continuity was tried and rejected in
   `docs/tuning-results.md`.)

A classifier trained on synthetic data couldn't learn its way round either problem. The rig has
neither the player-to-player spread nor the swaps, and the real set is 26 clips from 5 players.

## What the rig says each view can measure

The 90th-percentile error of each 2D measurement against the exact 3D value, at the true phase
frame, with the stance at the rig's 80° and the knees turning with the body (full table in the
report):

- **Contact measurements pass from nearly every view.** Elbow straightness, contact height,
  front knee and trunk tilt are all within 10° (0.1 body heights for height). The exceptions are
  the elbow from the toss side (11°) and the knee from a high camera behind (11°).
- **The trophy knee bend fails from every view, side-on included.** It's off by 27–30° from the
  hitting side and 26–35° from the toss side, because the knees bend diagonally to the camera,
  not across it.
- **The trophy elbow fails from every view:** 21–79°.
- **Trunk tilt at the trophy passes side-on** (2°) and from the front-diagonal hitting side (4°),
  and fails from the front and behind (17–19°).

So the ±10° rule would hide the trophy knee and elbow on side-on clips too. That conflicts with
the requirement that no side-on clip loses a measurement: the two targets can't both be met.

## What would work instead

- **Ask, don't guess.** An optional "Where was your camera?" question at upload gives the court
  view directly, and the labelled clips tier 2 needs.
- **A hidden-arm note that makes no claim about the view.** The hitting arm's visibility is
  measurable directly: it's below 0.4 at the trophy in 7 of 24 real clips. The note should say
  the arm was hard to see, not which side to film from, because two of those clips were filmed
  from the hitting side and the low visibility came from swapped labels.
- **Honest wording for the trophy angles everywhere.** They're approximate from any single
  camera, which the in-app limits already say. A second camera, filming at the same time, is the
  fix the depth study recommends.
