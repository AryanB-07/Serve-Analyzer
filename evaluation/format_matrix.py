"""Does every supported file type, with its quirks, analyse like the original clip?

Run inside the production image (it needs ffmpeg with its encoders), from the repository root:

    docker run --rm --platform linux/amd64 --user root -v "$PWD:/repo" -w /repo \\
      --entrypoint python serve-analyzer-app -m evaluation.format_matrix

Each real clip is re-encoded into many variants (containers, codecs, audio, rotation tags,
HDR, high frame rates, interlacing, stretched pixels, odd sizes, broken files). Each variant
goes through the full pipeline and is compared with the original: same orientation and
size, the same phases (allowing for compression and frame-rate changes), and browser-playable
result videos with one frame per analysed frame. Writes evaluation/reports/formats_<time>.md.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2

from serve_analyzer.errors import PipelineError
from serve_analyzer.pipeline import analyze
from serve_analyzer.video import fourcc

from . import real
from .sweep import REPORTS, commit_id

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
X265 = ["-c:v", "libx265", "-preset", "fast", "-crf", "20", "-tag:v", "hvc1", "-x265-params", "log-level=error"]


@dataclass
class Variant:
    name: str
    ext: str
    args: list[str]                      # ffmpeg output arguments
    feature: str                         # what real-world feature it mimics
    expect: str = "same"                 # same | rejected
    target_fps: float | None = None      # the frame rate the pipeline should end up analysing at
    input_args: list[str] = field(default_factory=list)
    post: str | None = None              # an extra step: "rotate:<deg>", "truncate", "cover"


VARIANTS = [
    Variant("mov-h264", ".mov", X264, "MOV with H.264 (older iPhones, most cameras)"),
    Variant("mov-hevc", ".mov", X265, "MOV with HEVC (iPhone default)"),
    Variant("mov-hevc-aac", ".mov", X265 + ["-c:a", "aac"], "iPhone MOV with an AAC audio track", input_args=["AUDIO"]),
    Variant("mov-hevc-10bit-hdr", ".mov", X265 + ["-pix_fmt", "yuv420p10le", "-color_primaries", "bt2020",
            "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"], "iPhone HDR: 10-bit HEVC, HLG"),
    Variant("mov-prores", ".mov", ["-c:v", "prores_ks", "-profile:v", "1"], "ProRes (iPhone Pro, editing exports)"),
    Variant("mov-rot90", ".mov", X265, "portrait iPhone: stored sideways, rotation tag 90", post="rotate:90"),
    Variant("mov-rot180", ".mov", X265, "phone held upside down: rotation tag 180", post="rotate:180"),
    Variant("mp4-rot270", ".mp4", X264, "portrait the other way: rotation tag 270", post="rotate:270"),
    Variant("mp4-h264", ".mp4", X264, "MP4 with H.264 (Android default)"),
    Variant("mp4-h264-aac", ".mp4", X264 + ["-c:a", "aac"], "Android MP4 with audio", input_args=["AUDIO"]),
    Variant("mp4-hevc", ".mp4", X265, "MP4 with HEVC (newer Android)"),
    Variant("mp4-av1", ".mp4", ["-c:v", "libaom-av1", "-cpu-used", "8", "-row-mt", "1", "-crf", "30"],
            "AV1 (some Android phones, screen recorders)"),
    Variant("mp4-60fps", ".mp4", X264 + ["-vf", "fps=60"], "60 fps", target_fps=60),
    Variant("mp4-120fps", ".mp4", X264 + ["-vf", "fps=120"], "120 fps (slow-motion capture)", target_fps=120),
    # A fine time base first: on a coarse one (1/25 s) the jittered timestamps collide and frames
    # are dropped, which is a different file, not a variable frame rate.
    Variant("mov-vfr", ".mov", X264 + ["-vf", "settb=1/90000,setpts='(N+0.3*sin(N))/(FRAME_RATE*TB)'",
            "-fps_mode", "vfr", "-video_track_timescale", "90000"],
            "variable frame rate (phones space frames unevenly)"),
    Variant("mov-hevc-10bit-hdr-rot90", ".mov", X265 + ["-pix_fmt", "yuv420p10le", "-color_primaries", "bt2020",
            "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"], "iPhone default: portrait 10-bit HDR HEVC",
            post="rotate:90"),
    Variant("mp4-odd-size", ".mp4", ["-vf", "crop=iw-1:ih-1", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "18", "-pix_fmt", "yuv444p"], "odd width and height"),
    Variant("mp4-cover-art", ".mp4", X264, "MP4 with an embedded cover image", post="cover"),
    Variant("mp4-truncated", ".mp4", X264 + ["-movflags", "+faststart"], "upload cut off at 70%", post="truncate"),
    Variant("m4v-h264", ".m4v", X264 + ["-f", "mp4"], "M4V (Apple exports)"),
    Variant("webm-vp9-opus", ".webm", ["-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "5", "-crf", "32",
            "-b:v", "0", "-c:a", "libopus"], "WebM VP9 with Opus audio", input_args=["AUDIO"]),
    Variant("webm-vp8", ".webm", ["-c:v", "libvpx", "-deadline", "good", "-cpu-used", "4", "-b:v", "2M"], "WebM VP8"),
    Variant("webm-live-no-duration", ".webm", ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8",
            "-b:v", "2M", "-live", "1"], "browser recording (MediaRecorder): no duration or index"),
    Variant("mkv-h264", ".mkv", X264, "MKV with H.264"),
    Variant("mkv-hevc-flac", ".mkv", X265 + ["-c:a", "flac"], "MKV with HEVC and FLAC audio", input_args=["AUDIO"]),
    Variant("avi-mjpeg-pcm", ".avi", ["-c:v", "mjpeg", "-q:v", "3", "-c:a", "pcm_s16le"],
            "AVI, MJPEG with PCM audio (action cameras, old cameras)", input_args=["AUDIO"]),
    Variant("avi-xvid", ".avi", ["-c:v", "mpeg4", "-vtag", "XVID", "-q:v", "3"], "AVI with Xvid"),
    Variant("3gp-h264", ".3gp", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-profile:v", "baseline",
            "-c:a", "aac", "-ar", "16000", "-ac", "1"], "3GP (older Android)", input_args=["AUDIO"]),
    Variant("mts-h264", ".mts", X264 + ["-f", "mpegts"], "MTS (AVCHD camcorders)"),
    # A camcorder records 60 fields a second, two per (interlaced) frame; the pipeline should
    # deinterlace them back into 60 full frames a second.
    Variant("mts-interlaced", ".mts", ["-vf", "fps=60,tinterlace=interleave_top,fieldorder=tff", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "18", "-flags", "+ildct+ilme", "-x264-params", "tff=1", "-f", "mpegts"],
            "interlaced camcorder video (1080i, 60 fields/s)", target_fps=60),
    Variant("mts-anamorphic", ".mts", ["-vf", "scale=iw*3/4:ih,setsar=4/3", "-c:v", "libx264", "-preset",
            "veryfast", "-crf", "18", "-f", "mpegts"], "stretched pixels (HDV 1440x1080 shown as 1920x1080)"),
    Variant("text-renamed-mp4", ".mp4", [], "a text file renamed to .mp4", expect="rejected", post="garbage"),
]

CLIPS = ["pex_side", "pex_front", "saque_1", "evd_clay_1", "fixture_front"]
# Contact (the hitting wrist's highest frame) is sharp: 2 frames. The trophy is the peak of a
# flat knee-bend curve, and any lossy re-encode moves it a few frames (plain H.264 moved it 5 on
# one clip), so it's judged within a quarter of a second.
CONTACT_TOLERANCE = 2      # frames, at the original frame rate
TROPHY_TOLERANCE_S = 0.25


def make_variant(src: Path, v: Variant, out: Path) -> None:
    if v.post == "garbage":
        out.write_text("not a video\n" * 2000)
        return
    inputs = ["-i", str(src)]
    maps = ["-map", "0:v:0"]
    if "AUDIO" in v.input_args:
        inputs += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
        maps += ["-map", "1:a:0", "-shortest"]
    stage = out if not v.post else out.with_name(f"stage{out.suffix}")
    if v.post and v.post.startswith("rotate:"):
        # Store the frames rotated the opposite way, then tag them to display upright.
        deg = int(v.post.split(":")[1])
        turn = {90: "transpose=1", 180: "transpose=1,transpose=1", 270: "transpose=2"}[deg]
        args = v.args + ["-vf", turn]
    else:
        args = v.args
    if any("setpts=" in a for a in args):  # the VFR variant
        args = [a.replace("FRAME_RATE", str(cv2.VideoCapture(str(src)).get(cv2.CAP_PROP_FPS))) for a in args]
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *inputs, *maps, *args, str(stage)], check=True, timeout=900)
    if v.post and v.post.startswith("rotate:"):
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-display_rotation", v.post.split(":")[1],
                        "-i", str(stage), "-c", "copy", str(out)], check=True)
    elif v.post == "cover":
        cover = out.with_name("cover.png")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x320",
                        "-frames:v", "1", str(cover)], check=True)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(stage), "-i", str(cover), "-map", "0",
                        "-map", "1", "-c", "copy", "-disposition:v:1", "attached_pic", str(out)], check=True)
    elif v.post == "truncate":
        data = stage.read_bytes()
        out.write_bytes(data[: int(len(data) * 0.7)])
    if stage != out:
        stage.unlink(missing_ok=True)


def run(path: Path, hand: str, out: Path) -> dict:
    t = time.time()
    try:
        r = analyze(path, hand, out)
    except PipelineError as exc:
        return {"status": "rejected", "code": exc.code, "message": str(exc)[:120], "seconds": time.time() - t}
    except Exception as exc:  # noqa: BLE001 - a crash is a finding
        return {"status": "crashed", "message": f"{type(exc).__name__}: {exc}"[:200],
                "trace": traceback.format_exc()[-600:], "seconds": time.time() - t}
    videos = {}
    for name in ("playback.mp4", "annotated.mp4"):
        cap = cv2.VideoCapture(str(out / name))
        videos[name] = (fourcc(out / name), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        cap.release()
    return {"status": "ok", "seconds": time.time() - t, "phases": r.phases.as_dict(), "n_frames": r.n_frames,
            "fps": r.fps, "size": (r.width, r.height), "videos": videos, "warnings": r.warnings}


def judge(base: dict, got: dict, v: Variant) -> list[str]:
    """Problems with a variant's result compared with the original clip's."""
    scale = v.target_fps / base["fps"] if v.target_fps and base["status"] == "ok" else 1.0
    if v.expect == "rejected":
        return [] if got["status"] == "rejected" else [f"expected a rejection, got {got['status']}"]
    if v.post == "truncate":
        # Either the cut removed the serve (rejected), or it's analysed with a warning.
        if got["status"] == "rejected":
            return []
        if got["status"] == "ok" and not any("looks incomplete" in w for w in got["warnings"]):
            return ["a cut-off file was analysed without the 'incomplete' warning"]
    if got["status"] != "ok":
        if base["status"] == "rejected" and got["status"] == "rejected":
            return []  # the original isn't accepted either (e.g. not a complete serve)
        return [f"{got['status']}: {got.get('message', '')}"]
    if base["status"] != "ok":
        return []
    problems = []
    bw, bh = base["size"]
    gw, gh = got["size"]
    if (gw > gh) != (bw > bh):
        problems.append(f"orientation changed: {bw}x{bh} -> {gw}x{gh}")
    if abs(gw / gh - bw / bh) > 0.02:
        problems.append(f"aspect ratio changed: {bw / bh:.3f} -> {gw / gh:.3f}")
    if v.post != "truncate":
        expected_frames = base["n_frames"] * scale
        if abs(got["n_frames"] - expected_frames) > max(3, 0.03 * expected_frames):
            problems.append(f"{got['n_frames']} frames, expected about {expected_frames:.0f}")
    for phase in ("trophy", "contact"):
        b, g = base["phases"][phase], got["phases"][phase]
        if b is None or v.post == "truncate":
            continue
        tolerance = CONTACT_TOLERANCE if phase == "contact" else TROPHY_TOLERANCE_S * base["fps"]
        if abs(scale - round(scale)) > 0.01:
            tolerance += 1  # e.g. 25 -> 60 fps repeats frames unevenly (2, 3, 2, 3...)
        if g is None:
            problems.append(f"no {phase} (original: {b})")
        elif abs(g / scale - b) > tolerance:
            problems.append(f"{phase} at {g} (original {b}, x{scale:.2f})")
    for name, (codec, frames, w, h) in got["videos"].items():
        if codec not in ("avc1", "h264"):
            problems.append(f"{name} is {codec}, not H.264")
        if abs(frames - got["n_frames"]) > 1:
            problems.append(f"{name} has {frames} frames for {got['n_frames']} analysed")
        if (w > h) != (gw > gh):
            problems.append(f"{name} orientation differs from the analysis")
    return problems


def main() -> None:
    clips = {c.id: c for c in real.load_clips()}
    chosen = [clips[i] for i in (sys.argv[1:] or CLIPS)]
    only = {n for n in os.environ.get("VARIANTS", "").split(",") if n}  # e.g. VARIANTS=mov-vfr,mp4-60fps
    # git can't read a repository mounted into the container, so the commit can be passed in.
    stamp = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{os.environ.get('COMMIT') or commit_id()}"
    rows, failures, results = [], 0, {}
    for clip in chosen:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            base = run(clip.path, clip.hand.value, tmp / "base")
            print(f"\n{clip.id}: original {base['status']} {base.get('size')} {base.get('fps')} fps "
                  f"phases {base.get('phases')}", flush=True)
            results[clip.id] = {"original": base}
            for v in VARIANTS:
                if only and v.name not in only:
                    continue
                path = tmp / f"{v.name}{v.ext}"
                try:
                    make_variant(clip.path, v, path)
                except subprocess.CalledProcessError as exc:
                    print(f"  {v.name:24s} SKIP (couldn't build: {exc.stderr or exc})", flush=True)
                    continue
                got = run(path, clip.hand.value, tmp / v.name)
                problems = judge(base, got, v)
                failures += bool(problems)
                results[clip.id][v.name] = {**got, "problems": problems}
                verdict = "OK " if not problems else "BUG"
                detail = "; ".join(problems) or (f"{got['status']} {got.get('size', '')} {got.get('phases', got.get('code', ''))}")
                print(f"  {v.name:24s} {verdict} {got['seconds']:5.1f}s  {detail}", flush=True)
                rows.append(f"| {clip.id} | {v.name} | {v.feature} | {'ok' if not problems else '**' + '; '.join(problems) + '**'} |")
                shutil.rmtree(tmp / v.name, ignore_errors=True)
                path.unlink(missing_ok=True)
    lines = [f"# File-type matrix — {stamp}", "",
             f"{len(rows)} variant runs, {failures} with problems. Compared with the original clip, "
             f"contact may move {CONTACT_TOLERANCE} frames and the trophy {TROPHY_TOLERANCE_S} s "
             "(at the original frame rate).", "",
             "| Clip | Variant | Mimics | Result |", "|---|---|---|---|", *rows]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"formats_{stamp}.md").write_text("\n".join(lines) + "\n")
    (REPORTS / f"formats_{stamp}.json").write_text(json.dumps(results, indent=1, default=str))
    print(f"\n{failures} of {len(rows)} variant runs had problems; report: evaluation/reports/formats_{stamp}.md")


if __name__ == "__main__":
    main()
