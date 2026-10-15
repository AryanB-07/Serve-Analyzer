# Decision log

The main choices behind Serve Analyzer: what was chosen, what else was considered, the evidence,
and what would change the decision. Numbers link to the reports and docs they come from.

## Computer vision

### 1. MediaPipe Pose (heavy model) on the server's CPU

- **Chosen:** Google's MediaPipe `PoseLandmarker`, heavy variant, in VIDEO mode, on CPU.
- **Considered:** the lite and full variants; 2D-to-3D lifting models (VideoPose3D, MotionBERT); a hosted vision API.
- **Evidence** (`docs/tuning-results.md`, round 3):
  - Lite and full are 2× faster (6.5 and 7.4 ms against 15.4 ms per frame), but both lose the behind-view clip.
  - Real contact error is 3.6 frames with lite, 3.3 with full and 0.46 with heavy.
  - The lifting models' weights are licensed for non-commercial research only (`docs/multiview-research.md`).
  - A hosted API would send users' videos to a third party, costs money per call, and breaks the Privacy Policy's promise that videos stay on our servers.
- **Trade-off:** MediaPipe ships Linux wheels for x86-64 only, so the app image is pinned to `linux/amd64`, and ARM (Graviton) servers are out.
- **What would change it:** a lighter model that keeps the behind-view clip, or a serve-specific model trained on our own labelled clips.

### 2. Angles from the 2D image, not MediaPipe's 3D landmarks

- **Chosen:** joint angles measured in the image plane (`angle_space = "image2d"`).
- **Considered:** MediaPipe's world landmarks (`world3d`), and depth rebuilt from bone lengths (`bone3d`).
- **Evidence** (`docs/mediapipe-depth.md`):
  - The published accuracy and three validation studies agree that monocular depth is the weakest axis, worst exactly when a limb points at the camera.
  - In our mirror test (flipping the video should not change the angles), 3D angles moved far more than 2D: 22–30° on a diagonal elbow, against 4–6°.
  - Bone-length rebuilding helped on synthetic data but was *less* consistent on real clips.
- **Trade-off:** 2D is accurate only from side-on, so the filming guide and the in-app limits say so.
- **What would change it:** a second camera. With two views, triangulated depth beats both, and the depth study says that, not more tuning, is the next real accuracy gain.

### 3. Phases found by rules, not a trained classifier

- **Chosen:** heuristic detectors for the trophy position, racket drop and contact (contact is the frame where the hitting wrist is highest), each a separate function.
- **Considered:** a learned phase classifier (a small GRU or 1D-CNN), trained with synthetic multi-view augmentation.
- **Evidence:** the labelled data is 24 serves from about six players. A classifier would learn those players and cameras. The rules are few and physically meaningful: contact is within 1 frame in 9 of 10 real clips across views (`docs/multiview-probe-results.md`).
- **What would change it:** a few hundred labelled clips. The "this result looks wrong" reports exist partly to collect them.

### 4. Rejecting clips that aren't a serve, with thresholds set from serves only

- **Chosen:** four shape checks: the hitting wrist above the head at contact, the toss hand below it, the toss peaking first, and the toss arm climbing. Each threshold is about 70% of the weakest real serve's value.
- **Evidence** (`docs/serve-check.md`):
  - Wrongly accepted non-serve windows went from 15/57 to 5/57, with all 24 real serves kept.
  - On a held-out set downloaded after the thresholds were fixed, it accepted none.
- **Known limits, shown in the app:**
  - smashes (3 of 4 windows) and high-finish backhands (2 of 11) pass;
  - a swing that misses the ball can't be told from a serve without tracking the ball.

### 5. Rejected: repairing MediaPipe's left/right swaps

- **Tried:** a two-state Viterbi relabelling of frames where the whole body's left and right flip.
- **Evidence:** it "repaired" genuinely fast arm swings. Contact error went from 0.46 to 0.7–5.5 frames, and it lost up to 2 serves.
- **Decision:** the code was removed. A change that makes the numbers worse doesn't ship, however reasonable it sounds.

### 6. How changes are judged: numbers before merging

- **Rule:** every CV change runs against two ground truths: synthetic serves filmed by virtual cameras, where the truth is exact, and hand-labelled real clips.
  - It must help, or at least not hurt, on both.
  - Experiments change one factor at a time, and the reports are committed under `evaluation/reports/`.
- **Why:** the synthetic data alone misses real failure modes (it never hides joints at the scored frames), and the real set alone is too small to trust.

### 6b. Asking where the camera was, instead of guessing

- **Tried:** estimating the camera position from the skeleton: the shoulder and hip lines' turn
  at the set position, minus the usual stance turn (`docs/view-detection.md`).
- **Evidence:**
  - Real clips: 77% side-on detection, 69% side, 42% category, against targets of 95/95/85.
  - Players' stance varies by about 90° between people, and MediaPipe swaps left and right in
    profile views, so the skeleton can't tell where the net is.
- **Chosen:** an optional question at upload, and a relaxed rule.
  - A measurement is hidden only when the rig's error for that position is wider than its good
    range; otherwise it's shown, marked approximate if it's over 10°.
  - People who skip the question see exactly what they did before.
- **What would change it:** labelled clips from the question, to tune or replace the rig's
  ratings with real ones.

## Video handling

### 7. Every common phone and camera format, converted only when needed

- **Chosen:** decode with OpenCV, and convert with a static ffmpeg build only when a file needs it:
  - AV1;
  - interlaced video, which is deinterlaced to full frames;
  - non-square pixels;
  - over 120 fps, or over 1920 px.
- **Evidence** (`docs/file-formats.md`): 160 runs across 5 clips and 32 variants. They found and fixed four format-specific bugs. Contact matched the original within 1 frame in 95% of runs.
- **Trade-off:** HDR is decoded without tone mapping until there are real iPhone HDR clips to tune it on. Tuning it on synthetic HDR made things worse.

### 8. Limits on length, frame rate and size, enforced on the server

- **Chosen:**
  - over 15 s is refused from the header, before any conversion;
  - over 120 fps is reduced to 120;
  - over 1920 px is scaled to fit.
  So an analysis is at most 1,800 frames of 1080p-sized video.
- **Why:** the browser checks length too, but anything in the browser can be bypassed, and the limits protect a server with 1–2 GB of memory. A 4K frame is four times a 1080p one.
- **Evidence:** decoding 4K HEVC on all cores peaked at 1.2 GB. With one decoding thread it peaked at 0.5 GB, at the same speed, so conversions use one.

### 9. Browser-playable result videos by piping frames into ffmpeg

- **Problem:** OpenCV's Linux wheels can't encode H.264, so result videos produced on the server were MPEG-4 Part 2, which browsers don't play.
- **Chosen:** raw frames piped into a static ffmpeg build: single-pass H.264, with the index at the front (faststart) so playback can start straight away, and x264 limited to 2 threads.
- **Considered:** Debian's ffmpeg package. It added about 2 GB to the image, against a few tens of MB for the static build.

## Backend

### 10. FastAPI, with Postgres as the job queue

- **Chosen:** the API and the queue both live in the database. Analyses double as jobs.
  - Workers claim one with a single `UPDATE … FOR UPDATE SKIP LOCKED`, and keep the claim alive with heartbeats.
  - A worker's writes only count while the claim is still its own.
- **Considered:** Redis with Celery or RQ.
- **Why:**
  - one fewer service on a 1 GB server;
  - jobs survive restarts with the data they belong to;
  - a stalled worker can't overwrite the work of the one that took its job over.
- The same code runs on SQLite for development, and CI runs the API tests on both.
- **What would change it:** many workers on many machines, where a dedicated broker's fan-out would matter.

### 11. Video bytes never pass through the API

- **Chosen:** the browser uploads and plays videos with short-lived signed URLs, straight to S3. With local storage, the same interface is served from signed local URLs.
- **Why:** the API stays small (about 160 MB) and never holds a 200 MB upload in memory. Moving to S3 is a configuration change, not a code change.
- **Trade-off:** a signed URL works for anyone holding it until it expires, as with any S3 presigned URL. That's documented.

### 12. Pose extraction in a short-lived child process

- **Problem:** MediaPipe's memory isn't returned to the system after a video, so a long-running worker grows.
- **Chosen:**
  - each analysis runs pose extraction in a spawned child process, which exits afterwards;
  - `malloc_trim` runs after each job;
  - `MALLOC_ARENA_MAX=2` is set in the image.
- **Evidence** (`docs/deploy-aws-free-tier.md`): the worker returns to about 250 MB between jobs and doesn't grow. The API never imports MediaPipe, which took it from 289 MB to 151 MB.

## Accounts, security and privacy

### 13. Server-side sessions, not JWTs

- **Chosen:**
  - a random token in an HttpOnly, Secure, `SameSite=Lax` cookie;
  - only the token's SHA-256 is stored;
  - sliding 30-day expiry, extended at most once a day.
- **Considered:** JWTs.
- **Why:** sign-out, password reset and account deletion must revoke sessions immediately, which stateless tokens can't do without a deny-list. A database leak doesn't expose live sessions.
- **Also:**
  - passwords are hashed with argon2id;
  - rate limits are counted in the database, so all API processes share them, and they store only hashes of IPs and emails;
  - emails are sent after the response, so the response time doesn't reveal whether an address has an account.

### 14. Defence in depth for the browser

- **Chosen:**
  - `SameSite=Lax` cookies plus an Origin check on every write, against CSRF;
  - a strict Content-Security-Policy, so only the site's own scripts, styles and media load. The inline theme script was moved to a file to allow it;
  - HSTS, `X-Frame-Options`, Permissions-Policy and COOP headers;
  - a 1 MB cap on JSON request bodies;
  - the interactive API docs hidden outside development.
- **Tested:** every browser test fails on any CSP violation.

### 15. Privacy by design

- **What we keep:**
  - original uploads are deleted after 30 days; results are kept until the person deletes them;
  - deleting an analysis or account queues its files in the same transaction, so a storage outage delays a deletion but never loses it.
- **What we don't do:** no analytics, no third-party scripts, and no request or IP logging.
- **What people can do themselves:** download all their data, change their email, and delete their account.
- **Error reporting** (Sentry's free plan or GlitchTip) is off unless configured, and runs on the server only:
  - errors only;
  - no request details, users, variables or source lines;
  - email addresses and tokens masked.
- **Accepted trade-off:** signup says when an email is already registered, as most sites' signups do.

## Frontend

### 16. React, TanStack Query, and API types generated from the backend

- **Chosen:** the frontend's TypeScript types are generated from FastAPI's OpenAPI schema, and CI fails if they drift.
  - TanStack Query handles caching, polling with backoff, and invalidation.
  - The skeleton is drawn on a canvas synced to the video's clock, and the charts use uPlot, which is small.
- **Why:** the API contract is enforced by the compiler instead of by hope. Polling backs off while a status is unchanged and speeds up on each stage change.

### 16b. Simple scores and advanced error bars, from the same numbers

- **Chosen:** two views of one analysis.
  - **Simple mode:** a 0–100 score per key position, mapped piecewise from the reference range
    so the score always falls in the same band as the label (tested at 180 values for every
    range).
  - **Advanced mode:** the exact angle with a likely range: the camera position's rig error
    plus the tracking noise around that moment, and MediaPipe's confidence in the weakest
    joint the measurement uses.
- **Why:** players want "how am I doing?", while coaches and interviewers want "how sure are
  you?". The error bars make the single-camera limits visible, instead of hiding them behind a
  precise-looking number. On the sample clip the front knee reads 86.2° with a likely range of
  58.7–113.7°.
- **Trade-off:** scores against placeholder reference ranges are only as meaningful as the
  ranges. The page says so.

### 16c. History scores worked out once, on the server

- **Chosen:**
  - the worker saves each serve's overall score and its five key-position scores in their own columns when the analysis finishes;
  - History's filters (upload time, score band, a key position's band) are query parameters on `GET /analyses`, run in SQL and paged with the same cursor;
  - older analyses are scored once by the hourly housekeeping job.
- **Considered:** filtering in the browser, using scores computed from each result. That's simpler, but every card would need its full results file, and filters would only cover the pages already loaded, so "show my good serves" would silently miss older ones.
- **Why:** filters have to be right across the whole history, not just the first page.
  - The score mapping is now in Python (`serve_analyzer/score.py`) as well as TypeScript.
  - Shared test vectors (`frontend/src/test/score_vectors.json`) are checked by both test suites, so the two can't drift apart.
  - Python rounds half up, as JavaScript's `Math.round` does.
- **Trade-off:** each score is fixed against the ranges the serve was analyzed with, which are saved in its results. That keeps it matching the serve's own results page, but new reference ranges only apply to new analyses.

### 16d. Profiles in their own table, and pictures prepared in the browser

- **Chosen:**
  - a `profiles` table keyed by the user, holding the public side of an account: username, display name, bio and picture. `users` keeps only sign-in details. A row appears the first time someone saves anything, so the many accounts from before profiles need no migration of their data.
  - usernames are 3–20 lowercase letters, digits and underscores, stored lower-cased under a unique index, with a reserved list (admin, support, settings…). Uniqueness is decided by the index, not a check-then-insert, so two people can't race to the same name.
  - the browser decodes the photo, crops it to a centred square, shrinks it to 512 px and re-encodes it as a JPEG. Re-encoding drops every bit of metadata, including the GPS position phones write into photos.
  - the API decodes nothing. It checks the JPEG's structure: square, 64–1024 px from the frame header, complete, and at most 1 MB (the proxy's limit for everything but videos). It removes any metadata segments (EXIF, XMP, ICC, comments) in plain Python, for clients that skip the browser. It's served as image/jpeg with nosniff.
  - changing the password in Settings keeps the current device signed in and signs out every other one.
- **Considered:**
  - columns on `users`: simpler today, but social features will add privacy settings, links to UTR, and so on, and those belong with the public profile, not the password hash;
  - uploading the original photo straight to storage, as videos are: it would mean storing photos with their location in them, plus a worker step to clean them up;
  - re-encoding on the server with OpenCV or Pillow, both already installed. Either adds 30–40 MB to the API process while handling a photo (measured), and the API is kept free of the image and video stack to fit a small server (`tests/test_footprint.py`). It would also mean decoding untrusted images on the server.
- **Why:** the profile is what other people will see once social features arrive, so it's kept apart from private data from the start. A picture never reaches storage with metadata in it, whichever client sent it.
- **Trade-off (pictures):** the server doesn't prove the image data decodes, only that the file is a well-formed, square, metadata-free JPEG. A broken one would just fail to show, and only its uploader could send it.
- **Trade-off:** a username someone gives up is free for anyone straight away. Once profiles are public, that allows impersonation; a cool-off period would fix it.

### 16e. Friends: mutual, found only by exact username, and blocks you can't detect (requests replaced by follows in 16j)

- **Chosen:**
  - mutual friendships (request, then accept), not one-way follows. A follow model makes everyone's data a broadcast; mutual means both people chose it.
  - one `connections` row per pair of people, whichever asked, under a unique index on the sorted pair of ids. Two requests can't exist between the same people, and if both ask at the same moment, the second one finds the first and accepts it.
  - people are found only by their exact username. There's no search by name, no directory and no suggestions, so nobody can browse the members. That matters with a minimum age of 13.
  - a block hides each person from the other completely. The blocked person gets the same 404 as for a username nobody has, so a block can't be detected by probing.
  - non-friends see only display name, username and picture; friends also see the bio; nobody sees serves yet.
  - consent comes from choosing a username: an account without one can't be found at all. Every account from before this feature has none, so nothing became visible without the person acting.
  - phones get a bottom tab bar for the main sections. The header can't hold a third link at 360 px, and messages will make four.
- **Considered:** search by display name (useful, but it lets strangers browse); "decline" remembered forever (stops repeat requests, but adds state; the hourly rate limit and blocking cover it for now).
- **Trade-off:** someone who declines a request can be asked again later. Blocking is the answer if that's unwanted.

### 16f. Sharing serve stats with friends: opt-in, worked out when asked

- **Chosen:**
  - three separate switches: serve stats, key-position averages, and a place on the leaderboard. All are off to start with; friends see a line saying you don't share rather than zeros.
  - the numbers come from the stored score columns each time a friend asks, never from a cache or a copy, so turning a switch off hides them straight away.
  - the leaderboard is friends only. Each person is ranked by the average of their latest 10 scored serves in the last 90 days, and needs 5 serves in that time to be ranked. Ties share a rank (1, 1, 3). Someone with too few serves is listed without an average, since the average of one or two serves would mislead.
  - every score shown to someone else carries the note that the reference ranges aren't validated yet.
- **Considered:**
  - a global leaderboard: a stranger-facing ranking is a different privacy promise, and the scores aren't validated;
  - ranking by best serve: easy to game with one lucky clip, while an average of recent serves rewards consistency;
  - storing each person's averages: faster, but a copy to keep in step, and it would outlive turning sharing off.
- **Comparing with a friend's serve** came with sending serves (16h): it needs a friend to open one of your analyses, so the owner check is extended once, for that.

### 16g. Messaging: friends only, polling, and reports that outlive deletion

- **Chosen:**
  - one-to-one conversations between accepted friends. A conversation is one row per pair, like a friendship; members are in their own table, so each person has a read position, and a group chat would fit later without a new design.
  - updates by polling: 5 s in an open conversation, 15 s for the list, 30 s for the badge.
  - unfriending keeps the conversation readable but closed, and says why. A block hides it from both people while it lasts, so the blocked person still can't tell the blocker exists. Unblocking brings it back, closed until they're friends again.
  - deleting a message clears its text for everyone and leaves a "Message deleted" marker. Deleting an account deletes the messages it sent; the other person keeps their own.
  - a report keeps a copy of the reported message and survives either account being deleted, with that account's id cleared. Otherwise the person reported could erase the evidence by deleting the message, or the account. Reports are kept a year, which the Privacy Policy states, and `python -m serve_api.reports --people` lists them.
  - rate limits are counted from the messages table itself (30 a minute, 500 a day), so busy conversations don't add a row to the attempts table for every message.
- **Considered:**
  - websockets or server-sent events: instant, but each open tab holds a connection on a single small server, and Caddy, the API and the tests would all need more work. Polling is a few cheap indexed queries. Push is the upgrade if conversations get busy.
  - messaging anyone by username: with a minimum age of 13, friends-only is the safer default.
  - keeping deleted messages' text for moderation: reports keep their own copy, so a deleted message can really be gone.
- **Trade-off:** polling means up to 5 s before a reply appears, and some traffic even when nothing has changed.

### 16h. Sending a serve: access that lives in the message

- **Chosen:**
  - a message can carry one of the sender's finished analyses. There's no separate share record: the message is the share. You can read an analysis if you own it, or if its owner sent it to you in a message that still exists, you're friends now, and there's no block (`Database.shared_by`). It's worked out on every request, so deleting the message, unfriending, blocking or deleting either account ends access straight away, with nothing to keep in step.
  - only the three read endpoints (summary, results, frames) accept that. Notes, retrying, deleting and reports stay behind the owner check, so the friend gets 404s, as for an analysis they can't see. Shared analyses don't appear in the friend's list or data download.
  - the friend sees the analysis without its note or filename ("Shared serve", shown as "Ann's serve"), and never gets the original upload, only the processed videos the results page plays.
  - only your own analyses can be sent, so a serve someone sent you can't be forwarded.
  - comparing with a friend's serve reuses the compare page, which only uses the read endpoints.
- **Considered:**
  - a share table with expiry: more control, but a second thing to revoke, and messages already have the lifetime people expect ("unsend").
  - public links: easy to forward to anyone, which is exactly what a 13+ product with videos of people shouldn't do.
- **Trade-off:** the access check costs a join per request on shared analyses. That's indexed (`messages_analysis`) and only runs when the viewer isn't the owner. And nothing stops a friend recording their screen, which the Privacy Policy says plainly.

### 16i. Suspension as "hidden from everyone", and usernames held after they're given up

- **Chosen:**
  - suspending an account (`python -m serve_api.moderate suspend`) ends its sessions, refuses sign-in, and hides it from everyone else. The check that hides blocked people (`hidden_between`) also hides suspended accounts, so every place that respects blocks (finding someone, conversations, shared serves, notifications) respects suspensions with no change. Friend lists, request counts and the leaderboard leave suspended accounts out too. Nothing is deleted, so unsuspending puts everything back.
  - sign-in tells a suspended person their account is suspended, but only after the password checks out, so a guesser learns nothing.
  - a username someone gives up is held for 30 days, and only they can take it back. Without that, renaming or deleting an account would let anyone take the old name and pose as that person to their friends.
  - notifications only for things with no badge of their own: a new follower, a follow back (now friends), a serve received. Messages already count on the Messages tab. Notifications about a request that's been cancelled or declined are deleted with it.
- **Considered:** deleting abusive accounts outright (what the checklist said before). It's irreversible, loses the evidence, and gives the person no way to appeal.
- **Trade-off:** there's no moderation screen yet, just a script on the server. That's fine for one operator; a dashboard is the next step if reports grow.

### 16j. Follows replace friend requests; friendship is derived

- **Chosen:**
  - one-way follows that need no approval. Two people are friends when each follows the other. It's worked out from the `follows` rows whenever it's needed (`Database.are_friends`), never stored, so it can't drift out of step: unfollowing someone who follows you ends the friendship, and removing a follower does too.
  - every access rule that said "friends" keeps saying it: messages, stats sharing, the leaderboard and sent serves all ask `are_friends`, now answered from follows. Shared serves stop opening the moment either side unfollows.
  - follows are idempotent. The primary key (follower, followee) makes a double tap a no-op, a check constraint refuses following yourself, and `PUT /follows/{username}` returns the same answer however many times it's sent.
  - "let people follow me" (off means only people you follow can follow you, i.e. back) replaces "let people send me requests". You still need a username to follow, so people can see who follows them.
  - existing data was converted by the migration: a friendship became a follow each way, and a pending request a follow from the person who asked. The downgrade rebuilds requests from the follows.
  - the lists (friends, followers, following) can be seen by their owner and the owner's friends, and nobody else: the API refuses (403) anyone who doesn't follow and get followed back. Others see only the counts. A friend's view leaves out anyone hidden from them (a block either way).
  - lists are cursor-paged in SQL: ordered by (since, user id), and a page asks for rows before the last one it saw. A friend's `since` is the later of the two follows, computed in the query (a CASE, the same on SQLite and Postgres), so even the friends list never loads in full.
  - a username is required at signup, created in the same transaction as the account so one can't exist without the other. A signed-out check (rate-limited by IP) lets the form say "available" as it's typed. Accounts from before then are sent to choose one before anything else, so every account ends up with one.
- **Why:** the product needs follows for feeds (following someone you don't know, as with any public profile), and one model for both avoids two relationships that could disagree.
- **Trade-off:** following needs no consent, so it's easier to attach yourself to a stranger than with requests. Following alone grants nothing beyond public posts: the bio, stats, messages and shared serves all need the follow back. Blocking and "let people follow me" are the controls.

### 16k. Posts: snapshots of serves, with the audience checked on every request

- **Chosen:**
  - a post is one of your analysed serves, not an arbitrary video: every post shows real analysis, and the upload, limits, conversion and thumbnails already exist and are tested.
  - a post is a snapshot. Creating it copies the analysis's skeleton video and thumbnail into the post's own storage (`posts/<id>/`), with its scores. Deleting the post deletes exactly that copy, with its likes and comments, and leaves the serve in My Serves; deleting the analysis later doesn't break the post. The snapshot never includes the note, the filename or the original upload.
  - two audiences: Friends (the default) and Public, meaning everyone signed in, not the open web. `visible_kinds(viewer, author)` is checked on every read, like and comment: hidden (a block either way, or a suspension) means nothing; friends means public and friends posts; anyone else gets public posts only. Ending a friendship ends access to friends posts at once, and a post you can't see is a 404, the same as one that doesn't exist.
  - videos and thumbnails go through the same short-lived signed URLs as everything else, so a friends-only video can't be guessed or kept as a link.
  - likes are one row per (post, person), so liking twice is a no-op; the UI updates at once and puts the like back if the server refuses. Comments come oldest first, cursor-paged; the author or the post's owner can delete one. Posts and comments can be reported, keeping a copy of the text.
  - the video doesn't load until it's played (`preload="none"` with the thumbnail as poster), so a page of posts doesn't download every video.
- **Considered:** a post that points at the analysis (no copy): cheaper, but deleting the post would then have to delete or orphan the analysis, and the post would break when the analysis was deleted.
- **Trade-off:** a copy of a few megabytes per post, made while the request waits. For S3, a server-side copy would avoid the download and re-upload.

### 17. Accessibility as a test, not a review

- **Chosen:**
  - axe-core scans every page type in both themes (WCAG 2.1 AA) on every push;
  - keyboard use is tested directly: the Help dialog's tabs, the focus trap and focus return, and the video shortcuts.
- **Evidence:** the first scan found button text at 3.6:1 contrast in the dark theme (AA needs 4.5:1), and phase labels at 3.1–3.9:1. Both are fixed.

## Deployment and testing

### 18. One small EC2 instance with Docker Compose and Caddy

- **Chosen:** one x86 instance (t3.small recommended) running Caddy, for HTTPS and the site; the API; the worker; and Postgres, all from one Compose file. A free DuckDNS name, and a free Brevo email plan.
- **Considered:**
  - ECS or Fargate: more moving parts, and Fargate isn't free;
  - Lambda: MediaPipe and ffmpeg make a large x86 bundle, there are cold starts, and the memory–CPU coupling doesn't fit;
  - RDS: the right move later, documented in `docs/deployment.md`.
- **Why:** it costs nothing on the free tier or credits, and one command sets it up (`scripts/server_setup.sh`).
- **Instance size, from the memory rehearsal** (`docs/deploy-aws-free-tier.md`): with the worst clips the limits allow, the whole stack peaks at about 1 GB.
  - A t3.small (2 GB) never swaps.
  - A t3.micro (1 GB) still finishes every analysis using the swap file, 15–25% slower.

### 19. Tests that run the real thing

- **Chosen:** unit and API tests, on both SQLite and Postgres, plus browser tests driving Chromium against the actual production images:
  - Postgres and the real worker and pipeline;
  - a Mailpit inbox for the emailed links;
  - a backup restore and the server setup script, each in its own test.
- **Evidence:** these caught bugs the unit tests couldn't:
  - the client treating empty 202 responses as network errors, which broke password reset in production;
  - a sign-out race that only appeared on slower CI machines;
  - the Postgres connection limit being exceeded by the test suite;
  - the setup script dying on a server with no crontab.
