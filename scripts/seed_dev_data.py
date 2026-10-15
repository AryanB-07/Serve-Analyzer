"""Fill a development database with realistic accounts and analyses, for trying the app by hand.

    uv run python scripts/seed_dev_data.py            # add the seed accounts (replacing earlier ones)
    uv run python scripts/seed_dev_data.py --remove   # take them out again

Uses the same settings as the API (SERVE_API_DATABASE_URL, SERVE_API_DATA_DIR, storage), so run
it against the database the local API uses. Every seed account's email starts with "seed-" and
ends in @example.com; nothing else is touched, and --remove deletes only those accounts with
their files.

The real pipeline runs once on tests/fixtures/sample_serve.mp4 (about half a minute). Every
analysis is built from that output, so each one plays the real video and has real frames.
To make History's scores and filters worth trying, the five key positions' measurements are
varied per analysis, and labels, feedback and scores are worked out again from the varied
values. The charts still show the sample clip's angles, so a varied card's number won't match
the chart at that phase.

Deliberately awkward rows, the kind real data accumulates:
- results files from before camera positions, confidence and scores (schema 2), with no
  History scores, so housekeeping's backfill has to score them;
- failed analyses, including an error code the frontend has never heard of;
- an upload that never finished, and original videos past the 30-day retention;
- long, multi-line, emoji and HTML-looking notes and filenames;
- a "this result looks wrong" report; an unverified account from before the Terms were
  recorded; an account with nothing in it;
- profiles: one with a name, bio and picture, ones without a picture or name, and one that
  has never set one (like every account from before profiles existed);
- friends: a friendship, a request waiting for an answer, a block, and different choices of
  what to share with friends; a conversation with an unread reply, a deleted message and a
  serve sent to a friend; a report; notifications; a suspended account that was the player's
  friend (it must stay hidden from everyone).
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import tempfile
import uuid
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

import cv2
import numpy as np
from argon2 import PasswordHasher
from sqlalchemy import select, update

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serve_analyzer import feedback  # noqa: E402
from serve_analyzer.pipeline import analyze  # noqa: E402
from serve_analyzer.pose import extract_pose_sequence  # noqa: E402
from serve_analyzer.reference import assess, load_ranges, to_labels  # noqa: E402
from serve_analyzer.score import KEY_POSITIONS, key_scores  # noqa: E402
from serve_analyzer.view import UNREADABLE  # noqa: E402
from serve_api import keys, migrate  # noqa: E402
from serve_api.avatars import clean  # noqa: E402
from serve_api.convert import counts_from_labels, public_message  # noqa: E402
from serve_api.db import Database, now  # noqa: E402
from serve_api.purge import analysis_prefixes  # noqa: E402
from serve_api.settings import Settings  # noqa: E402
from serve_api.storage import make_storage  # noqa: E402
from serve_api.tables import analyses, users  # noqa: E402

CLIP = ROOT / "tests" / "fixtures" / "sample_serve.mp4"
PASSWORD = "seed-password"
PREFIX, DOMAIN = "seed-", "@example.com"
VIEWS = [None, "side_hitting", "front", "behind", "front_diagonal_hitting"]
COPIED = [keys.PLAYBACK, keys.ANNOTATED, keys.THUMBNAIL, keys.FRAMES]

NOTES = [
    "Worked on tossing further in front. Felt better.",
    "Windy today 🌬️ so the toss drifted. Don't read too much into this one.",
    "New strings (Luxilon 4G, 52 lbs).\nFirst serve felt great.\nSecond serve still too flat.",
    "Coach said: bend the knees more, keep the tossing arm up longer. Compare with last week's.",
    "<b>not bold</b> <script>alert('if you see a popup, notes are not escaped')</script> & ampersands",
    "Long note: " + " ".join(["Focus on the trophy position and staying sideways until the hip drive."] * 13),
    "Ça va bien — 发球练习 — práctica de saque ✔︎",
]
NOTES[5] = NOTES[5][:1000]  # exactly at the limit

FILENAMES = [
    "IMG_{n:04d}.MOV", "serve_{n}.mp4", "PXL_20260{m}12_1{n:05d}.mp4", "practice day {n}.mov",
    "Saque fuerte – cámara lateral ({n}).mp4",
    "a-very-long-filename-from-a-camera-app-that-never-heard-of-short-names-session-{n}-final-FINAL.mp4",
]


def say(msg: str) -> None:
    print(msg, flush=True)


# --- the pipeline, once per camera position -----------------------------------------------------

def run_pipeline(work: Path) -> dict[str | None, Path]:
    """The sample clip analysed as filmed from each seeded camera position. The pose is extracted
    once and reused, and the videos are rendered once."""
    cache: dict[str, object] = {}

    def cached_pose(info, model_path):
        if "pose" not in cache:
            cache["pose"] = extract_pose_sequence(info, model_path)
        return cache["pose"]

    out: dict[str | None, Path] = {}
    for view in VIEWS:
        target = work / (view or "unknown")
        analyze(CLIP, "right", target, pose_extractor=cached_pose, camera_view=view,
                render_video=view is None)
        out[view] = target
        say(f"  analysed as filmed from {view or 'an unknown position'}")
    for view, target in out.items():  # videos and thumbnail from the one rendered run
        for name in COPIED:
            if not (target / name).exists():
                shutil.copy(out[None] / name, target / name)
    return out


# --- varying one analysis -----------------------------------------------------------------------

def vary(results: dict, rnd: random.Random, quality_profile: float) -> dict:
    """The results with the key positions moved, so each analysis scores differently.
    ``quality_profile`` from 0 (mostly off) to 1 (mostly good)."""
    ranges = load_ranges()
    metrics = json.loads(json.dumps(results["metrics"]))
    for metric, phase in KEY_POSITIONS.items():
        rng = results["ranges"].get(phase, {}).get(metric)
        if not rng:
            continue
        (g0, g1), (b0, b1) = rng["good"], rng["borderline"]
        roll = rnd.random()
        if roll < 0.05:
            value = None  # not measured this time (out of frame, say)
        elif roll < 0.05 + 0.75 * quality_profile:
            value = rnd.uniform(g0, g1)
        elif roll < 0.8:
            value = rnd.choice([rnd.uniform(b0, g0), rnd.uniform(g1, b1)])
        else:
            spread = max(b1 - g1, g0 - b0, (g1 - g0) / 2)
            value = rnd.choice([b0 - rnd.uniform(0, spread), b1 + rnd.uniform(0, spread)])
        if value is not None:
            value = round(value, 3 if metric == "wrist_height" else 1)
        metrics.setdefault(phase, {})[metric] = value

    out = dict(results, metrics=metrics)
    assessments = assess(metrics, ranges)
    quality = results.get("quality")
    readable = [a for a in assessments if not quality or quality.get(a.phase, {}).get(a.metric) != UNREADABLE]
    out["labels"] = to_labels(assessments)
    out["feedback"] = [asdict(f) for f in feedback.generate(readable)]
    out["scores"] = key_scores(out)
    return out


def as_schema_2(results: dict) -> dict:
    """What a results file looked like before camera positions, confidence and scores."""
    old = {k: v for k, v in results.items() if k not in ("camera_view", "quality", "confidence", "scores")}
    old["schema_version"] = 2
    old["feedback"] = [{k: v for k, v in f.items() if k != "plain"} for f in results["feedback"]]
    return old


# --- writing rows ---------------------------------------------------------------------------------

class Seeder:
    def __init__(self, settings: Settings) -> None:
        self.db = Database(settings.sqlalchemy_url)
        migrate.upgrade(self.db.engine)
        self.storage = make_storage(settings)
        self.hasher = PasswordHasher()

    def seed_user_ids(self) -> list[str]:
        with self.db.engine.connect() as conn:
            return list(conn.execute(select(users.c.id).where(
                users.c.email.like(f"{PREFIX}%{DOMAIN}"))).scalars())

    def remove(self) -> int:
        ids = self.seed_user_ids()
        for user_id in ids:
            self.db.delete_user(user_id, analysis_prefixes, [keys.avatar_prefix(user_id)])
        for purge_id, prefix in self.db.pending_purges():
            self.storage.delete_prefix(prefix)
            self.db.finish_purge(purge_id)
        return len(ids)

    def user(self, name: str, *, verified: bool = True, terms: str | None = "2026-10-14",
             age_days: float = 150) -> str:
        row = self.db.create_user(f"{PREFIX}{name}{DOMAIN}", self.hasher.hash(PASSWORD), terms_version=terms)
        assert row is not None, f"{name} already exists"
        if verified:
            self.db.mark_email_verified(row["id"])
        with self.db.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == row["id"]).values(
                created_at=now() - timedelta(days=age_days)))
        return row["id"]

    def profile(self, user_id: str, *, username: str, display_name: str | None = None, bio: str | None = None,
                photo_colour: tuple[int, int, int] | None = None) -> None:
        """A profile, with a generated picture (initials on a colour) when ``photo_colour`` is given."""
        fields: dict = {"username": username, "display_name": display_name, "bio": bio}
        if photo_colour:
            image = np.zeros((512, 512, 3), np.uint8)
            image[:] = photo_colour
            initials = "".join(w[0] for w in (display_name or username).split()[:2]).upper()
            size = cv2.getTextSize(initials, cv2.FONT_HERSHEY_SIMPLEX, 6, 14)[0]
            cv2.putText(image, initials, ((512 - size[0]) // 2, (512 + size[1]) // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        6, (255, 255, 255), 14, cv2.LINE_AA)
            key = keys.avatar_key(user_id, uuid.uuid4().hex)
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / keys.AVATAR).write_bytes(clean(cv2.imencode(".jpg", image)[1].tobytes()))
                self.storage.publish(Path(tmp), key.rsplit("/", 1)[0])
            fields["avatar_key"] = key
        assert self.db.save_profile(user_id, **fields) != "username_taken", f"{username} is taken"

    def analysis(self, user_id: str, *, filename: str, age_days: float, hand: str = "right",
                 camera_view: str | None = None, status: str = "succeeded", files: Path | None = None,
                 results: dict | None = None, scored: bool = True, note: str | None = None,
                 error_code: str | None = None) -> str:
        row = self.db.create(user_id, hand, filename, "video/mp4", 4_000_000, camera_view=camera_view)
        analysis_id = row["id"]
        fields: dict = {"status": status, "created_at": now() - timedelta(days=age_days),
                        "updated_at": now() - timedelta(days=age_days) + timedelta(seconds=40)}
        if status == "succeeded":
            assert files is not None and results is not None
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                for name in COPIED:
                    shutil.copy(files / name, out / name)
                (out / keys.RESULTS).write_text(json.dumps(dict(results, hand=hand)))
                self.storage.publish(out, keys.output_prefix(analysis_id))
            fields["counts"] = counts_from_labels(results["labels"], results.get("quality"))
            if scored:
                scores = results.get("scores") or key_scores(results)
                fields.update(overall_score=scores["overall"], key_scores=scores["key"])
        elif status == "failed":
            fields.update(error_code=error_code, error_message=public_message(error_code or "INTERNAL", ""))
        if status != "awaiting_upload" and age_days > 30:  # as the worker's 30-day retention would have
            fields["input_deleted_at"] = fields["created_at"] + timedelta(days=30)
        if note:
            fields["note"] = note
        with self.db.engine.begin() as conn:
            conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(**fields))
        return analysis_id


def seed(seeder: Seeder, outputs: dict[str | None, Path], rnd: random.Random) -> dict[str, int]:
    base = {view: json.loads((path / keys.RESULTS).read_text()) for view, path in outputs.items()}
    made: dict[str, int] = {}

    # A regular player: four months of practice, improving over time.
    player = seeder.user("player")
    seeder.profile(player, username="seed_player", display_name="Sam Seedling", photo_colour=(160, 90, 40),
                   bio="Club player, four months into rebuilding my serve.\nWorking on the toss and the knee bend.")
    n = 0
    for i in range(46):
        age = 120 - i * 2.6 + rnd.uniform(-0.8, 0.8)
        view = rnd.choice(VIEWS)
        results = vary(base[view], rnd, quality_profile=min(1.0, 0.15 + i / 46))
        note = NOTES[i % len(NOTES)] if i % 4 == 0 else None
        name = FILENAMES[i % len(FILENAMES)].format(n=1000 + i, m=(i % 9) + 1)
        seeder.analysis(player, filename=name, age_days=max(age, 0.02), camera_view=view,
                        files=outputs[view], results=results, note=note)
        n += 1
    # From before camera positions and scores: an old results file and no History scores yet.
    for i in range(4):
        old = as_schema_2(vary(base[None], rnd, quality_profile=0.5))
        seeder.analysis(player, filename=f"old_upload_{i}.mp4", age_days=150 - i, files=outputs[None],
                        results=old, scored=False,
                        note="Uploaded before scores existed." if i == 0 else None)
        n += 1
    for code in ("NOT_A_SERVE", "NO_PERSON_DETECTED", "VIDEO_TOO_LONG", "A_CODE_FROM_THE_FUTURE"):
        seeder.analysis(player, filename=f"failed_{code.lower()}.mp4", age_days=rnd.uniform(1, 90),
                        status="failed", error_code=code)
        n += 1
    seeder.analysis(player, filename="never_finished_uploading.mov", age_days=0.01, status="awaiting_upload")
    made["player"] = n + 1

    # A report on the newest succeeded analysis.
    with seeder.db.engine.connect() as conn:
        newest = conn.execute(select(analyses).where(analyses.c.user_id == player,
                                                     analyses.c.status == "succeeded")
                              .order_by(analyses.c.created_at.desc()).limit(1)).mappings().one()
    seeder.db.save_report(dict(newest), "wrong_phases", "The trophy marker is a few frames late.")

    # A left-handed player with a handful of serves.
    lefty = seeder.user("lefty", age_days=40)
    seeder.profile(lefty, username="seed_lefty", display_name="Lee Lefty")  # no picture
    for i in range(5):
        seeder.analysis(lefty, filename=f"lefty_{i}.mp4", hand="left", age_days=30 - i * 6,
                        camera_view="side_hitting", files=outputs["side_hitting"],
                        results=vary(base["side_hitting"], rnd, quality_profile=0.6))
    made["lefty"] = 5

    newbie = seeder.user("new", age_days=0.5)  # signed up, nothing analysed yet
    seeder.profile(newbie, username="seed_newbie")
    made["new"] = 0

    # Friends: the player and the lefty are friends; the newcomer has asked the player; the
    # lefty has blocked a fifth account, which has a username but nothing else.
    friendship = seeder.db.request_connection(lefty, player)
    seeder.db.accept_connection(friendship["id"], player)
    seeder.db.request_connection(newbie, player)
    pest = seeder.user("blocked", age_days=20)
    seeder.profile(pest, username="seed_blocked", display_name="Blocked Ben")
    seeder.db.block(lefty, pest)
    made["blocked"] = 0
    # Sharing: the player shares everything; the lefty shares stats and is on the leaderboard
    # with 5 serves (just enough); the newcomer shares nothing.
    seeder.db.save_profile(player, share_stats=True, share_positions=True, on_leaderboard=True)
    seeder.db.save_profile(lefty, share_stats=True, on_leaderboard=True)

    # A conversation between the two friends, with an unread reply, a deleted message, and a
    # long one; and a report the blocked account's behaviour earned.
    conv = seeder.db.conversation_with(player, lefty, create=True)
    for sender, text in [
        (lefty, "Saw your serve from Tuesday. The knee bend looks much deeper!"),
        (player, "Thanks! Still working on the toss, it keeps drifting left."),
        (player, "Ignore that last bit, wrong drill."),
        (lefty, "Try tossing with your palm up and hold the arm up longer. " * 6),
        (lefty, "Hit on Saturday? 10am at the club 🎾"),
    ]:
        seeder.db.add_message(conv["id"], sender, text.strip())
    # The player sends the lefty their best recent serve (it opens read-only for the lefty).
    with seeder.db.engine.connect() as conn:
        best = conn.execute(select(analyses.c.id).where(analyses.c.user_id == player, analyses.c.status == "succeeded",
                                                        analyses.c.overall_score.is_not(None))
                            .order_by(analyses.c.overall_score.desc()).limit(1)).scalar_one()
    seeder.db.add_message(conv["id"], player, "My best one yet. Compare it with yours?", best)
    deleted = next(m for m in seeder.db.messages_page(conv["id"], limit=20) if (m["body"] or "").startswith("Ignore"))
    seeder.db.delete_message(deleted["id"], player)
    seeder.db.mark_read(conv["id"], lefty)
    seeder.db.save_user_report(reporter_id=lefty, reported_id=pest, reported_username="seed_blocked",
                               message_id=None, message_body=None, reason="spam", note="Kept sending requests.")

    # Notifications, as the API would have made them.
    seeder.db.notify(player, "request_received", newbie)
    seeder.db.notify(lefty, "request_accepted", player)
    seeder.db.notify(lefty, "serve_received", player, conv["id"])

    # A suspended account that was the player's friend and messaged them: hidden from everyone now.
    banned = seeder.user("suspended", age_days=60)
    seeder.profile(banned, username="seed_suspended", display_name="Sus Pended")
    link = seeder.db.request_connection(banned, player)
    seeder.db.accept_connection(link["id"], player)
    banned_chat = seeder.db.conversation_with(banned, player, create=True)
    seeder.db.add_message(banned_chat["id"], banned, "buy followers at …")
    seeder.db.notify(player, "request_accepted", banned)
    seeder.db.save_user_report(reporter_id=player, reported_id=banned, reported_username="seed_suspended",
                               message_id=None, message_body="buy followers at …", reason="spam", note=None)
    seeder.db.suspend(banned, "Spam (seed data)")
    made["suspended"] = 0
    seeder.user("unverified", verified=False, terms=None, age_days=200)  # before the Terms were recorded
    made["unverified"] = 0
    return made


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="only remove the seed accounts")
    parser.add_argument("--seed", type=int, default=7, help="random seed, for the same data each time")
    args = parser.parse_args()

    settings = Settings()
    seeder = Seeder(settings)
    say(f"database: {seeder.db.engine.url.render_as_string(hide_password=True)}")
    removed = seeder.remove()
    if removed:
        say(f"removed {removed} earlier seed accounts")
    if args.remove:
        return

    say("running the pipeline on the sample serve…")
    with tempfile.TemporaryDirectory(prefix="seed-") as tmp:
        outputs = run_pipeline(Path(tmp))
        made = seed(seeder, outputs, random.Random(args.seed))

    say("\nSign in with any of these (password: %s):" % PASSWORD)
    for name, count in made.items():
        say(f"  {PREFIX + name + DOMAIN:<30} {count} analyses")
    say("\nThe 4 old-format analyses have no History scores yet, like real ones from before scores")
    say("existed: the worker scores them when it starts (housekeeping), so start it to see them.")


if __name__ == "__main__":
    main()
