# Serve Analyzer

Upload a side-on video of one tennis serve and get an interactive breakdown of your technique:
your skeleton tracked frame by frame, joint angles at each phase of the serve, how they compare
with reference ranges, and plain-English feedback on what to work on. You can also put two
serves side by side, synced by phase, to see whether you're improving.

It's built as three parts: a Python pose-analysis pipeline, a FastAPI backend with a job worker,
and a React frontend.

## Features

- **Pose tracking:** MediaPipe pose landmarks for every frame, cleaned (low-confidence points
  dropped, short gaps filled) and smoothed with a Savitzky–Golay filter.
- **Phase detection:** finds the trophy position, racket drop and contact.
- **Metrics and feedback:** knee flexion, hitting-arm extension, trunk tilt and contact height,
  each labelled good, borderline or needs work against reference ranges, with 3–4 ranked
  coaching points.
- **Interactive results page:**
  - the video with a canvas skeleton overlay, coloured by status, with raw vs smoothed landmarks
  - a phase timeline you can scrub, frame-accurate controls (0.25×–1×) and keyboard shortcuts
  - angle-over-time charts synced to the video, with phase shading and reference bands
  - metric cards and feedback that jump the video to the moment they describe
- **Upload flow:** a filming guide, checks in the browser before uploading, a direct upload
  with a real progress bar, live processing stages, and friendly error screens with retry.
- **History and compare:** past analyses with summaries; compare two serves with the videos
  aligned at trophy and contact, a before/after table and overlaid charts.
- **Mock mode:** the whole frontend runs on real pipeline output with no backend, for demos
  and development.
- **Accessibility:** dark and light themes, keyboard navigation, status shown by shape and
  text as well as colour, and layouts that work on a phone.

## Screenshots

> _Placeholder: add screenshots or a GIF of the results page, the compare view and the
> upload flow here._

## Architecture

```
 Browser (React)                 FastAPI (serve_api)            Worker (serve_api.worker)
 ───────────────                 ───────────────────            ─────────────────────────
 POST /analyses        ───────►  create record, return
                                 signed upload URL
 PUT video (progress)  ───────►  storage (local; S3 later)
 POST /analyses/{id}/start ───►  status = queued  ──────────►  claim job, run pipeline
 GET /analyses/{id}  (poll)  ◄──  status and stage   ◄──────────  report each stage
 GET …/result, …/frames      ◄──  results.json, frames.json ◄──  serve_analyzer writes outputs
```

- **`serve_analyzer/`: the pipeline.** Plain Python with no web dependencies. It writes
  `results.json` (metrics, labels, feedback), `frames.json` (per-frame landmarks and angle
  series), an H.264 playback copy of the video, an annotated video and a thumbnail.
- **`serve_api/`: the backend.** FastAPI, Postgres or SQLite through SQLAlchemy with Alembic
  migrations (the analyses table doubles as the job queue), local storage with S3-style signed
  URLs, and a separate worker process. Swapping in S3 and SQS changes the storage and queue
  code, not the frontend.
- **`frontend/`: React, TypeScript and Vite.** Tailwind for styling, TanStack Query for
  server data, uPlot for charts. The TypeScript types are generated from the API's OpenAPI
  schema.

## Quick start

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** for Python. It installs Python 3.11 for the project
  automatically.
- **Node 22.** The version is pinned in `frontend/.node-version`; any Node version manager
  works (fnm, nvm, Volta).
- macOS (Apple Silicon), Linux or Windows.

### Install

```bash
git clone https://github.com/AryanB-07/Serve-Analyzer.git
cd Serve-Analyzer
uv sync --extra dev --extra api
cd frontend && npm install && cd ..
```

The pose model (`pose_landmarker_heavy.task`, ~30 MB) is downloaded automatically the first
time a video is analysed, to `~/.cache/serve_analyzer/`.

### Option A: frontend only, with mock data

There's no Python to run. The UI serves real pipeline output from `frontend/public/mock/` and
simulates uploads and processing.

```bash
cd frontend
npm run dev:mock
```

Open http://localhost:5173 and click **Or open the demo analysis**. To see the error screen,
upload a file whose name contains `fail`. Mock mode starts signed in as a demo user. After
signing out, any email and password signs back in.

### Option B: full app

Run each command in its own terminal, from the repository root:

```bash
uv run uvicorn serve_api.app:create_app --factory --reload   # 1. API on :8000
uv run python -m serve_api.worker                            # 2. worker
cd frontend && npm run dev                                   # 3. UI on :5173 (proxies /api to :8000)
```

Open http://localhost:5173 and create an account (any email and a password of 8 or more
characters). Then choose your serving hand and upload a clip. To try it without your own
footage, use `tests/fixtures/sample_serve.mp4` with **Right-handed**. Accounts, uploads and
results are stored in `var/`; delete that folder to reset.

| Problem | Fix |
|---|---|
| Upload finishes but stays on "Queued" | The worker (terminal 2) isn't running. |
| The page loads but data never appears | The API (terminal 1) isn't running; check its output. |
| `Address already in use` on :8000 | `lsof -ti:8000 \| xargs kill` |
| Worker logs "waiting for database migrations" | Start the API (it applies them), or run `uv run python -m serve_api.migrate`. |

### Database

With no configuration the app uses a SQLite file, `var/serve_api.sqlite3`, which needs no setup.
To use Postgres instead (as in production), set `SERVE_API_DATABASE_URL` for both the API and
the worker:

```bash
docker compose up -d                 # local Postgres 16, or use any Postgres you have
export SERVE_API_DATABASE_URL=postgresql://serve:serve@localhost:5432/serve_analyzer
```

The API applies pending migrations when it starts, and the worker waits until they're done. To
run them as a separate step instead (for example during a deploy), set
`SERVE_API_AUTO_MIGRATE=0` and run `uv run python -m serve_api.migrate`.

To change the schema, edit `serve_api/tables.py`, then generate and review a migration:

```bash
uv run alembic revision --autogenerate -m "add users table"
```

| Variable | Default | Meaning |
|---|---|---|
| `SERVE_API_DATABASE_URL` | SQLite in `var/` | `postgresql://user:password@host:5432/db` or `sqlite:///path` |
| `SERVE_API_ENV` | `development` | Any other value requires `SERVE_API_SECRET` to be set |
| `SERVE_API_SECRET` | a development-only value | Signs upload and download URLs |
| `SERVE_API_AUTO_MIGRATE` | `1` | `0` stops the API from migrating at startup |
| `SERVE_API_DATA_DIR` | `var` | Where uploads, results and the SQLite file are stored |
| `SERVE_API_COOKIE_SECURE` | on unless `SERVE_API_ENV=development` | `1`/`0` forces the session cookie's `Secure` flag |
| `SERVE_API_ALLOWED_ORIGINS` | none | Extra origins allowed to send POST/PUT/DELETE, comma-separated; only needed if a proxy rewrites `Host` |
| `SERVE_API_DAILY_ANALYSIS_LIMIT` | `20` | New analyses each user may create per rolling 24 hours |
| `SERVE_API_MAX_ACTIVE_ANALYSES` | `2` | Analyses each user may have queued or processing at once |
| `SERVE_API_STORAGE` | `local` | `local` keeps files in `SERVE_API_DATA_DIR`; `s3` uses a bucket |
| `SERVE_API_S3_BUCKET`, `SERVE_API_S3_REGION` | none | The bucket, when `SERVE_API_STORAGE=s3` (credentials come from the usual AWS variables or a role) |
| `SERVE_API_S3_ENDPOINT_URL` | AWS | Only for S3-compatible services (R2, MinIO) |

### Accounts

`POST /auth/signup`, `POST /auth/login`, `POST /auth/logout` and `GET /auth/me` provide email
and password accounts:

- Passwords are hashed with argon2id: at least 8 characters, no composition rules.
- A session is an HttpOnly, `SameSite=Lax` cookie holding a random token. The database stores
  only the token's SHA-256, so a database leak doesn't expose live sessions. Logging out deletes
  the session on the server.
- Sessions last 30 days from the last visit, extended at most once a day.
- Login is limited to 10 failed attempts per email per 15 minutes, and signup plus login to 30
  requests per IP per 10 minutes. The counters live in each API process's memory.
- POST, PUT and DELETE requests from another origin are refused (CSRF protection on top of
  `SameSite`).

Every `/analyses` route requires a session and only works on the signed-in user's own analyses.
Anyone else's analysis returns 404, exactly like an ID that doesn't exist, so IDs can't be
probed. Video and image URLs are signed and short-lived (15 minutes to upload, up to 6 hours to
view), and they're only issued after the ownership check. Like S3 presigned URLs, anyone holding
one can use it until it expires.

Analyses created before accounts existed are assigned to the oldest account when the database is
migrated. If there are no accounts yet, they go to a placeholder owner that can't be signed in to.

### Job queue and limits

The `analyses` table doubles as the job queue, and any number of workers can share it:

```bash
uv run python -m serve_api.worker   # start as many as you like, on one machine or several
```

- A worker claims one queued job at a time. On Postgres, `FOR UPDATE SKIP LOCKED` means two
  workers never get the same job.
- While a job is processing, its worker refreshes a heartbeat every 20 seconds. If a worker
  crashes or loses its connection, the job goes back on the queue once its heartbeat is 2 minutes
  old, and another worker picks it up.
- Each claim carries a random token, and a worker can only update a job while it still holds that
  claim. A worker that stalled past the 2 minutes can't overwrite the result of the worker that
  took over.
- A job that has been claimed 3 times without finishing (for example, a video that crashes the
  worker) is marked failed instead of being retried forever. Retrying it from the app gives it 3
  fresh attempts.
- A worker runs the pipeline in a private scratch folder and publishes the outputs only if it
  still holds the claim, so a stalled worker can't overwrite files either.
- Once an hour, each worker deletes uploads that never arrived within a day, expired sessions,
  and old sign-in attempts.

Each analysis costs real CPU time, so each user is limited to 20 new analyses per rolling 24 hours
and 2 queued or processing at once. Going over either limit returns 429 with a message the app
shows. Both limits are configurable (see the table above). The check and the write happen in one
transaction that locks the user's row (`SELECT … FOR UPDATE` on Postgres; SQLite takes its
write lock), so simultaneous requests can't slip past a limit.

Login rate limits are stored in the database, so every API server shares them and they survive
restarts. Rows store a hash of the IP or email, not the address itself.

## Deploying

`docs/deployment.md` walks through running the app on a server with HTTPS, managed Postgres and
S3: `docker compose -f deploy/docker-compose.yml up -d --build`, after filling in
`deploy/.env`.

## Filming a serve that analyses well

- Film **side-on**: the camera at right angles to the direction you serve.
- Stand **5–10 m** away, with the camera at hip height and steady (a tripod or the fence).
- Keep your **whole body** in frame, with room above your head for the racket.
- **One serve per clip**, 15 s max; **30 fps or more** (60 fps or slow motion is better).

## Command-line pipeline

The pipeline also works on its own, without the web app:

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

Videos over 15 s or under 24 fps are rejected with an error code and exit code 2. Outputs:
`results.json`, `frames.json`, `playback.mp4`, `annotated.mp4` and `thumbnail.jpg`.

From Python:

```python
from serve_analyzer import analyze

result = analyze("serve.mp4", "right", "results/")
print(result.phases, [item.text for item in result.feedback])
```

## Tests

```bash
uv run pytest                        # Python: pipeline, API, worker, schema sync
uv run pytest -m "not integration"   # skip the tests that run the real pipeline on video
SERVE_API_DATABASE_URL=postgresql://… uv run pytest   # the same suite on an empty Postgres database

cd frontend
npx vitest run                       # unit and component tests (`npm test` to watch)
npm run typecheck                    # TypeScript
npm run check:api                    # generated types are up to date with openapi.json
```

Backend tests cover the full upload → worker → result flow on a real clip, signed URLs,
status transitions, pagination and edge cases (tiny clips, missing landmarks, portrait video).
Frontend tests cover:
- the pure maths: coordinate mapping with letterboxing, frame/time conversion, phase
  alignment for compare mode, polling backoff
- the playhead store
- upload validation and flow
- components: timeline seeking, metric cards, feedback, processing states, history selection

The fixture clip `tests/fixtures/sample_serve.mp4` is CC BY 4.0 (see
`tests/fixtures/ATTRIBUTION.md`).

## Project layout

```
serve_analyzer/          pipeline: pose, cleaning, angles, phases, metrics, feedback, export
  data/reference_ranges.json
serve_api/               FastAPI app, auth, schemas, database and job queue, migrations, signed-URL storage, worker
scripts/                 export_openapi.py, make_mock_fixtures.py
tests/                   Python tests and the sample clip
frontend/
  openapi.json           API contract (generated)
  public/mock/           mock-mode fixtures (generated from the real pipeline)
  src/
    api/                 generated types, HTTP + mock clients, TanStack Query hooks
    playhead/            playhead store, video clock, compare-mode follower
    lib/                 pure logic: coords, time, phases, timeline, align, charts, metrics
    features/
      upload/            filming guide, drop zone, validation, upload flow
      processing/        stage progress and error screens
      results/           video + overlay, timeline, controls, charts, cards, feedback
      history/  compare/
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /analyses` | Create an analysis; returns a signed `PUT` URL for the video |
| `PUT <signed url>` | Upload the video directly to storage |
| `POST /analyses/{id}/start` | Queue the analysis after the upload finishes |
| `GET /analyses/{id}` | Status: `queued → extracting_pose → analyzing → rendering → succeeded / failed` |
| `POST /analyses/{id}/retry` | Re-queue a failed analysis |
| `GET /analyses?cursor=` | History, newest first, cursor-paginated |
| `GET /analyses/{id}/result` | Metrics, labels, ranges, feedback, warnings and video URLs |
| `GET /analyses/{id}/frames` | Per-frame landmarks (raw and smoothed) and angle series |

Interactive docs are at http://localhost:8000/docs while the API is running. Failures carry
a code (`NO_PERSON_DETECTED`, `NOT_A_SERVE`, `VIDEO_TOO_LONG`, `FPS_TOO_LOW`, `UNREADABLE_VIDEO`,
`INTERNAL`) that the UI turns into specific advice. `NOT_A_SERVE` says which part of a serve is
missing (for example, no ball toss before the swing).

## How the analysis works

| Stage | Module | What it does |
|---|---|---|
| Validate | `video.py` | Checks duration and frame rate; takes dimensions from a decoded frame so portrait phone video is handled |
| Pose | `pose.py` | MediaPipe Tasks `PoseLandmarker` in VIDEO mode |
| Clean | `preprocessing.py` | Drops low-visibility points, fills gaps of ≤5 frames, Savitzky–Golay smoothing |
| Angles | `angles.py` | Front/back knee flexion, hitting elbow angle, trunk tilt, wrist height in body heights |
| Serve check | `phases.py` | Rejects clips that aren't a serve: the toss must rise and peak before contact, and at contact the hitting wrist must be above the head with the toss arm down (see `docs/serve-check.md`) |
| Phases | `phases.py` | Contact = hitting wrist highest; trophy = deepest knee bend before contact with the toss arm raised; racket drop = most flexed elbow in between |
| Assess | `metrics.py`, `reference.py`, `feedback.py` | Values at each phase, labels from `reference_ranges.json`, ranked feedback rules |
| Export | `export.py`, `render.py`, `pipeline.py` | `results.json`, `frames.json`, playback/annotated videos, thumbnail |

## Design notes

- **One playhead, few re-renders.** A small store holds the current frame. The video reports
  the frame actually on screen (`requestVideoFrameCallback`), and the controls send commands
  through the store. The canvas, chart cursors and timeline marker update from store
  subscriptions outside React's render cycle, so playback doesn't re-render the page.
- **Coordinate and time maths are pure and tested.** Landmarks are mapped into the letterboxed
  picture area, not the element box. Frame/time conversion allows for floating-point error
  (1.16 s × 25 fps is 28.999…).
- **Compare mode uses a time warp.** It's piecewise-linear between the phases both clips
  share, and real-time outside them. The second video follows by adjusting its playback speed
  and is only re-seeked when it drifts, which avoids stutter.
- **Contract-first API.** Pydantic models are the source of truth. TypeScript types are
  generated from them, and a test fails if the committed schema drifts from the API.
- **Signed URLs, as with S3.** The browser uploads straight to storage with progress, and
  upload URLs close once analysis starts. Moving to S3 only changes the storage module.

## Development workflow

- After changing API schemas, run `npm run gen:api` in `frontend/`. It regenerates
  `openapi.json` and `src/api/schema.d.ts`; `tests/test_openapi_sync.py` fails until you do.
- After changing pipeline output, run `npm run gen:mocks` to rebuild the mock fixtures.
- `.venv/`, `var/` (local data) and `results/` are git-ignored.

## Known limitations

**Analysis**

- **2D pose from one camera.** Angles are measured in the image plane, so they're accurate
  only when the camera is side-on and level.
- **Occlusion.** Limbs on the far side of the body, the net, or a partly out-of-frame body
  cause missing metrics and undetected phases.
- **The racket and ball aren't tracked.** Contact is the frame where the wrist is highest.
  At 30 fps the true contact usually falls between frames.
- **The phase heuristics assume one serve per clip.** Each detector is a separate function so
  it can be replaced by a learned classifier.
- **The reference ranges are placeholders.** They're literature-inspired, not validated, and
  not adjusted for age, height or level.
- **Trunk tilt is unsigned,** and a constant frame rate is assumed.
- **mediapipe is pinned below 1.0.** 1.0.x aborts on macOS arm64
  ([google-ai-edge/mediapipe#6356](https://github.com/google-ai-edge/mediapipe/issues/6356)).

**Web app**

- **No password reset or email verification yet.** Signup also reveals whether an email is
  already registered.
- **Uploads that never arrive stay in history** as "Upload not finished" for up to a day before
  the worker deletes them.
- **Signed video URLs work for anyone holding one** until they expire (up to 6 hours), like any
  S3 presigned URL.
- **With S3, a video can be replaced after its analysis has started,** until the 15-minute upload
  link expires. That only affects the uploader's own analysis.
- **Mock mode keeps new uploads in memory,** so they disappear on page reload.
- **The upload limits (200 MB, 15 s) are defined in both the frontend and the backend.**
