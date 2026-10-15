# Prompt: social features

<!--
How to use this file:
- Edit anything marked [EDIT], and delete options you don't want.
- Delete whole phases you don't want yet; the phases are written to stand alone.
- Paste everything below the line into Claude Code, or say "follow docs/prompts/social-features.md".
- Lines inside these comment markers are notes for you, not part of the prompt.
-->

---

I want to add social features to Serve Analyzer: connect with other players, see each other's
serve scores, averages and ranks, message each other, and send each other serves. Build it in
the phases below. **Stop after each phase:** show me what you built, the test results, and
anything you had to decide, and wait for me to say go before starting the next one.

## Where the app is now

- Accounts have only an email and a password. There are no usernames, display names or
  pictures yet.
- Everything a user owns is private to them. Every analysis endpoint goes through one owner
  check in `serve_api/app.py` (`db.get_owned`).
- History (being renamed "My Serves") stores each serve's overall score and five key-position
  scores in their own columns (`overall_score`, `key_scores`). Notes on serves are private.
- The scores come from **placeholder reference ranges** that haven't been validated yet
  (`serve_analyzer/data/reference_ranges.json`).
- The minimum age is 13. Users under 18 need a parent's or guardian's permission (Privacy
  Policy, "Children and other people in your videos").
- It deploys to one small EC2 instance with Docker Compose and Caddy. Email isn't set up for
  launch yet (no domain).
- Existing patterns to reuse:
  - rate limits: `RateLimiter` in `serve_api/auth.py`;
  - "report a problem": `result_reports` and `serve_api/reports.py`;
  - cursor-paginated lists: `GET /analyses`;
  - seed data and the existing-data checker: `scripts/seed_dev_data.py` and
    `scripts/check_dev_data.py`;
  - the data download (`/auth/me/export`) and account deletion.

## Before Phase 1: profiles

Social features need a public identity. If it isn't built yet, build the Profile page first:
- a unique username: [EDIT: 3–20 characters, lowercase letters, digits and underscores,
  case-insensitive, changeable]
- a display name that's separate from the username;
- a short bio;
- a profile picture.

Settings shows the email (read-only), changes the password, display name and username, and
keeps the data download and account deletion. [EDIT: keep or remove the existing
change-email flow.] Existing accounts have no username, so the app has to work without one
and prompt for it before any social feature is used.

## Decisions I've made

<!-- Change any of these. Anything not decided here: recommend an option with the trade-offs,
     then go with your recommendation unless it's hard to undo. -->

- **Connections:** [EDIT: mutual "friends" (request → accept) | one-way "follow"]. Default:
  mutual friends.
- **Who can find me:** [EDIT: search by exact username only | search by name too]. Nobody is
  listed publicly, and there's no "people you may know".
- **Who can send me requests:** [EDIT: anyone | nobody, I share a link or code instead].
- **What friends see of my serves:** [EDIT: pick] overall average, trend over time, best score,
  number of serves, per-position averages, individual serves. Each is a setting I can turn
  off. Notes are never shared.
- **Ranks:** [EDIT: rank among my friends only | also a global leaderboard]. Default: friends
  only.
  - Ranked on [EDIT: the average of my last 10 finished serves].
  - At least [EDIT: 5] serves to be ranked.
  - [EDIT: within the last 90 days].
  - Opt-out per user.
- **Messaging:** one-to-one, text, between accepted connections only. [EDIT: group chats later
  or never.]
- **Serves in messages:** I can send one of my own analyses. Arbitrary photo or video uploads
  aren't allowed in messages: no media we'd have to moderate.
- **Real-time:** [EDIT: polling first (TanStack Query, about 5–10 s on the open conversation,
  slower elsewhere) | server-sent events | websockets]. Default: polling. Say what would make
  it worth upgrading.
- **Users under 18:** [EDIT: no messaging for under-18s | messaging only with accepted
  connections, same as everyone | collect date of birth at signup]. Whatever I pick, explain
  the trade-off before building messaging.

## Phase 1: connections

- Find someone by username, then send, accept, decline or cancel a request. Remove a
  connection, and block someone. A blocked person can't find, request, message or see you,
  and isn't told they're blocked.
- A connections page with tabs for connections, incoming requests and sent requests, and a
  count of pending requests in the navigation.
- A public profile page per user: what they show to connections, versus the minimum shown to
  everyone else (display name, username, picture).
- Privacy settings for the choices above.

## Phase 2: friends' stats and ranks

- On a connection's profile: the stats they share (from "What friends see"). They're worked out
  on the server from the stored score columns, never by loading results files.
- A friends leaderboard using the rank rules above, with "you" highlighted. Explain what each
  number means, and show the minimum-serves rule when someone isn't ranked yet.
- Every score shown to someone else carries the same note the results page has: the reference
  ranges are placeholders. [EDIT: or hide ranks until I've validated the ranges.]
- Comparing one of my serves with a connection's shared serve, if they share individual serves:
  reuse the compare page, read-only for theirs.

## Phase 3: messaging

- Conversations listed newest first, with unread counts. A conversation view that loads older
  messages on scroll. Messages are [EDIT: up to 2,000 characters].
- Sent, delivered and read state: [EDIT: read receipts on | off | a setting].
- I can delete my own message [EDIT: for everyone | only for me].
- Report a message, or a person: a reason and an optional note, stored for me to review, with
  a script like `serve_api/reports.py` to list them. Reporting offers to block.
- Rate limits on requests and messages per user, using the existing `RateLimiter`.
- Ending a connection, or blocking, stops new messages. [EDIT: the old conversation stays
  readable | it's hidden.]

## Phase 4: sending serves

- In a conversation, pick one of my finished analyses to send. The other person can open it
  read-only: the video with the skeleton, phases, metrics and feedback. They can't see my
  note, retry, delete, report a wrong result or download the original.
- Access is a share record that the owner check honours, extended in the one place it lives.
  It's read-only, and I can revoke it. It ends when the analysis or either account is deleted,
  or when the connection ends [EDIT: or keep it].
- Shared videos use the existing short-lived signed URLs. Make sure a URL can't be reused to
  reach other files.
- [EDIT: optional] "Send to a friend" from the results page.

## Later, not now (keep it possible)

- UTR's Engage API: link a UTR account, and show the level and recent matches on the profile.
  Leave room in the profile model, but don't call UTR or store UTR data yet. I'll check the
  API's terms and cost first. All APIs must be free.
- Coaches: a coach-player relationship with more access than a friend.
- Email notifications, once email is set up.

## Safety and privacy (required)

- Private by default. Everything shared is opt-in, and turning a setting off takes effect
  straight away, including for shares and stats already seen.
- Every new endpoint checks who's asking. Write tests proving a stranger, a blocked user and an
  ex-connection each get nothing, in the style of `tests/test_ownership.py`. Check for IDOR on
  every id in a URL or body.
- **Account deletion:** say what happens to my messages in other people's conversations, then
  do it.
  - [EDIT: deleted along with my account | kept, shown as from "Deleted user"].
  - Shares, connections, requests and blocks are removed.
- **Data download:** add connections, blocks, requests, messages I sent and received,
  shares, and reports I made.
- Update the Privacy Policy and Terms (what's shared, with whom, messaging rules, reporting)
  and bump the terms version. Changing what other people can see needs fresh consent: explain
  how existing users are asked.
- No real names, emails or ages shown to anyone but the user themselves.

## How to build it

- Follow the existing patterns:
  - SQLAlchemy Core tables, with an Alembic migration per phase;
  - indexes for every list query;
  - cursor pagination;
  - Pydantic schemas, with regenerated TypeScript types (`npm run gen:api`, `check:api`);
  - TanStack Query hooks;
  - the mock client kept in step, so `npm run dev:mock` still works.
- It has to work on both SQLite and Postgres. Add every new API test file to CI's Postgres list.
- No new heavy dependencies without asking me first. Reuse what's installed (FastAPI,
  SQLAlchemy, OpenCV for images).
- Keep the single-server deploy working. If a choice needs Redis, a queue or a second
  service, stop and ask.
- Mobile-first layouts with no sideways scrolling at 360 px. The header is already full on
  phones, so the new pages need a navigation pattern that fits; propose one.
- Existing data must keep working: old accounts without a username, old analyses, and the
  seed accounts. Extend `scripts/seed_dev_data.py` so the seed accounts are connected, have
  pending requests, conversations and shares. Extend `scripts/check_dev_data.py` to load the new
  pages and endpoints for every account.

## Testing (each phase, twice, before telling me it's done)

- Python tests on SQLite and on Postgres: permissions, blocking, rate limits, pagination,
  deletion and export.
- Vitest for the new components and hooks.
- Playwright e2e on the Docker stack with two browser contexts as two different users:
  request → accept → see stats → message → send a serve → open it → block → everything stops.
- axe accessibility scans of every new page, in both themes.
- Type checks, `check:api`, the production build, and `check_dev_data.py` on the seeded
  database.
- If anything existing got worse (speed, a test, a page), tell me before committing.

## Docs

- `docs/decisions.md`: an entry for each real choice (mutual vs follow, polling vs push, how
  shares extend the owner check, what deletion does to messages). I need to defend these in
  interviews, so include what you considered and why.
- README: features and the API table. The launch checklist: anything I must do before launch,
  such as reviewing reports and the moderation plan.

## Working with me

- Commit to main and push only when I say so, as me, with no co-author line.
- When you're unsure, recommend one option with its trade-off rather than listing every
  possibility. Ask only when the choice is mine to make (privacy, safety, product).
