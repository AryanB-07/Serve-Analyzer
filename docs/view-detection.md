# Telling the camera view from the landmarks

Tier 1 of the multi-view plan: work out where the camera was from the skeleton alone, then
report only what that view can measure. **Automatic detection didn't meet its targets, so the
app asks instead** ("What shipped instead", below). This page records what was tried, the
numbers and why, so the next attempt starts from the evidence.

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

## What shipped instead: ask, and relax the rule

**The question.** The upload form asks "Where was your camera?". It's optional, and offers
eight positions on a small top-down court, mirrored for left-handers, plus "Not sure". The
answer is stored with the analysis (`camera_view`), included in the data download and in
`python -m serve_api.reports`. Over time that's the labelled data tier 2 needs.

**The rule** (`serve_analyzer.view.measurement_quality`). Each measurement is rated from the
rig's error for the chosen position (`serve_analyzer/data/view_reliability.json`, generated by
`python -m evaluation.views table`):

| Rating | When | What the results do |
|---|---|---|
| **measured** | error ≤ 10° (0.1 body heights) | as before |
| **approximate** | error ≤ the width of the measurement's good range | shown with "≈" and "approximate from this angle" |
| **unreadable** | error wider than the good range, so the good/borderline/off label would be noise | "Can't be read from this angle"; no score, feedback or skeleton colour; counted as unknown in History |

The "good range" yardstick is the relaxed version of the original ±10° rule, which would have
hidden the trophy knees from every view, side-on included. A note above the measurements says
which ones the position can't read and which are approximate, with a link to the filming guide
unless the camera was already where the guide says. With no answer, nothing changes except a
one-line tip.

**A hidden-arm note.** "Your hitting arm was hard to see around the trophy position, so its
angles there may be missing or rough" appears when the hitting elbow and wrist average below 0.4
visibility. It deliberately doesn't say which side to film from (see "Why", point 2).

### What it changes, measured

- **With no answer:**
  - all 26 real clips give identical phases, measurements, labels and feedback before and after;
  - 6 clips gain the hidden-arm note.
- **If every real clip had been given its labelled position** (24 complete serves):
  - 19 of the 100 cards shown become "can't be read", and 31 become approximate;
  - 24 of 79 feedback points are dropped, usually replaced by the next most important one.
  - **Side-on clips lose nothing:** `evd_clay_1` and `evd_clay_3` keep every card, two of them
    approximate. `pex_side`, from the tossing side, loses its front-knee card.
  - Front-corner (hitting side) and back-corner (tossing side) clips lose both knee cards.

### Open questions (flagged for review)

- **The rig rates some positions above side-on.** From behind, and from a back corner on the
  hitting side, nothing is unreadable, and the knees read within 10° from that corner. That's
  because the rig's players are turned 75–80° at the trophy, so a camera behind the baseline
  sees them side-on. Real players turn anywhere from −20° to 90°, so the filming guide's advice
  (side-on, hitting-arm side) is unchanged until real labelled clips confirm or refute it.
- **The elbow at the trophy can't be read from the front or side-on (hitting side)** by the
  rig: 43–72° error. The arm bends towards the lens. It isn't one of the five cards, so on real
  clips this only drops feedback: 5 of the 12 front-view clips lose an elbow point.
- **The ratings assume the rig's stance.** With the stance varied like real players' (the second
  table in the report), almost every trophy measurement fails from every view.
