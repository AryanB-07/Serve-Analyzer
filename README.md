# Serve Analyzer

Upload a side-on video of one tennis serve and get back:

- an annotated MP4 with a skeleton overlay, the current serve phase and key joint angles,
- joint-angle metrics at the **trophy**, **racket drop** and **contact** phases,
- a good / borderline / off label for each metric against reference ranges,
- 3–4 points of plain-English feedback.

This is phase 1: a local Python pipeline and CLI. It has no web or cloud dependencies, so a
later API or queue worker can import it directly.

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.11 for the project if needed.

```bash
uv sync --extra dev
```

The pose model (`pose_landmarker_heavy.task`, ~30 MB) is downloaded on first run to
`~/.cache/serve_analyzer/`.

## Usage

```bash
uv run python -m serve_analyzer analyze path/to/video.mp4 --hand right --out results/
```

| Option | Default | Meaning |
|---|---|---|
| `--hand {right,left}` | required | The player's hitting hand |
| `--out DIR` | `results/` | Where outputs are written |
| `--ranges FILE` | packaged file | Custom reference ranges JSON |
| `--smooth-ms MS` | `150` | Savitzky–Golay window; `0` disables smoothing |
| `--model {lite,full,heavy}` | `heavy` | PoseLandmarker model size |
| `--debug-plots` | off | Also save a before/after smoothing plot of the hitting wrist |

Videos must be at most 15 s long and at least 24 fps. Anything else is rejected with an error
and exit code 2.

Outputs in `--out`:

- `results.json`: phase frame indices, metrics per phase, labels, feedback, and warnings
  (for example a phase that could not be detected).
- `annotated.mp4`: an H.264 video with the overlay.
- `smoothing_wrist.png`, with `--debug-plots` only.

From Python:

```python
from serve_analyzer import analyze

result = analyze("serve.mp4", "right", "results/")
print(result.phases, result.feedback)
```

## Web app (in progress)

Needs Node 22 (`frontend/.node-version`) in addition to uv.

```bash
uv sync --extra dev --extra api
cd frontend && npm install
```

**Frontend only, with mock data** (no Python needed):

```bash
cd frontend && npm run dev:mock        # http://localhost:5173
```

**Full stack**, in three terminals:

```bash
uv run uvicorn serve_api.app:create_app --factory --reload   # API on :8000
uv run python -m serve_api.worker                            # runs queued analyses
cd frontend && npm run dev                                   # http://localhost:5173, proxies /api
```

After changing API schemas, run `npm run gen:api` in `frontend/` to regenerate
`openapi.json` and the TypeScript types. `tests/test_openapi_sync.py` fails until you do.
`npm run gen:mocks` rebuilds the mock fixtures from the real pipeline.

## How it works

| Stage | Module | What it does |
|---|---|---|
| Validate | `video.py` | Checks duration and frame rate |
| Pose | `pose.py` | MediaPipe Tasks `PoseLandmarker` in VIDEO mode; stores `(frames, 33, [x, y, visibility])` in pixels |
| Clean | `preprocessing.py` | Sets low-visibility points to NaN, fills gaps of ≤5 frames linearly, smooths each run of valid frames with Savitzky–Golay |
| Angles | `angles.py` | Front and back knee flexion, hitting elbow angle, trunk tilt from vertical, wrist height in body heights |
| Phases | `phases.py` | Contact = hitting wrist highest; trophy = maximum knee flexion before contact with the toss arm raised; racket drop = most flexed elbow between the two |
| Assess | `metrics.py`, `reference.py`, `feedback.py` | Value at each phase, then a label from `data/reference_ranges.json`, then ranked feedback rules |
| Output | `render.py`, `pipeline.py` | Annotated video and `results.json` |

`pipeline.analyze_sequence()` runs every stage after pose extraction with no file I/O, so it
can be tested on synthetic landmark arrays.

## Tests

```bash
uv run pytest                      # everything (~3 s)
uv run pytest -m "not integration" # unit tests only
```

The integration test runs the full pipeline on `tests/fixtures/sample_serve.mp4`, a CC BY 4.0
clip (see `tests/fixtures/ATTRIBUTION.md`).

## Known limitations

- **2D pose from one camera.** Angles are measured in the image plane. They match the true
  joint angles only when the limb moves roughly parallel to the camera, so the camera needs
  to be side-on, level, and far enough away to keep the whole body in frame.
- **Occlusion and the far side of the body.** Limbs on the far side get low visibility and
  are often dropped. Nets, other players, or a partly out-of-frame body cause missing
  metrics and undetected phases.
- **The racket and ball are not tracked.** "Contact" means the frame where the hitting wrist
  is highest, which approximates ball contact. At 30 fps the real contact usually falls
  between frames, and motion blur makes wrist tracking least reliable exactly there.
  Higher frame rates help.
- **The phase heuristics assume one serve per clip.** Several serves, or a clip that ends
  before contact, will confuse them. Each detector is a separate function so it can be
  replaced by a learned classifier.
- **The reference ranges are placeholders.** They are rough, literature-inspired values, not
  validated, and not adjusted for age, height or playing level.
- **Trunk tilt is unsigned.** It doesn't separate a sideways lean from a forward or backward
  lean.
- **Constant frame rate is assumed.** Phone videos with variable frame rates get approximate
  timestamps.
- **mediapipe is pinned below 1.0.** mediapipe 1.0.x aborts on macOS arm64 when creating
  vision tasks ([google-ai-edge/mediapipe#6356](https://github.com/google-ai-edge/mediapipe/issues/6356)).
