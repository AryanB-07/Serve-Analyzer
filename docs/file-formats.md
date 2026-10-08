# Supported video files

People upload whatever their phone or camera produced. This page lists what works, which file
quirks the pipeline corrects, and how that was tested.

## What's accepted

| Container | Typical source | Codecs tested |
|---|---|---|
| `.mov` | iPhone (the preferred type), cameras, editing apps | H.264, HEVC (8- and 10-bit), ProRes |
| `.mp4`, `.m4v` | Android, most apps, Apple exports | H.264, HEVC, AV1 |
| `.webm` | browsers, screen recorders | VP8, VP9 |
| `.mkv` | cameras, converters | H.264, HEVC |
| `.avi` | action cameras, older cameras | MJPEG, Xvid (MPEG-4) |
| `.3gp` | older Android phones | H.264 |
| `.mts`, `.m2ts` | AVCHD camcorders | H.264, including interlaced and HDV |

Audio is ignored, whatever it is (AAC, Opus, FLAC and PCM were tested).

The browser decides the upload's type from the file extension, because browsers report these
types inconsistently. The API accepts exactly the types in `UploadContentType`
(`serve_api/schemas.py`).

## Quirks the pipeline corrects

`serve_analyzer/video.py`, `probe_or_convert` and `stream_fixes`:

| Quirk | Without a fix | What happens |
|---|---|---|
| **Rotation tags** (portrait phone video is stored sideways and tagged 90°, 180° or 270°) | Analysed sideways | OpenCV applies the tag when decoding; tested at 90°, 180° and 270° |
| **AV1** | OpenCV can't decode it | Converted to H.264 with ffmpeg first |
| **No length in the header** (WebM recorded in a browser) | OpenCV reports a frame count of about −2.7 × 10¹⁷ | Treated as unknown; ffmpeg rewrites the file with a proper header |
| **Interlaced video** (1080i camcorders record 50 or 60 half-frames a second) | Fast motion is combed; analysed at 25 or 30 fps | Deinterlaced into one full frame per field (`bwdif`), so 1080i60 is analysed at 60 fps |
| **Non-square pixels** (HDV stores 1440×1080 frames for 1920×1080 display) | The player looks 25% thinner, which distorts every angle | Rescaled to square pixels |
| **Odd width or height** | H.264 can't encode it | Result videos lose one pixel row or column |
| **High frame rates** (60, 120 fps) | — | Analysed at full rate; the time-based windows are in seconds, so phases line up |
| **Variable frame rate** (phones space frames unevenly) | — | Frames are analysed in order, and the result videos play back at a constant rate |
| **A cover image stored as a second video stream** | — | The real video stream is used |
| **A file that ends early** (a cut-off copy) | Analysed as if complete | If far fewer frames decode than the header promises, the results warn that the file looks incomplete |

Result videos are always browser-playable H.264 (OpenCV's Linux build can't write it, so frames
are piped into ffmpeg), with one frame per analysed frame.

## How it was tested

`python -m evaluation.format_matrix`, run inside the production image (instructions are in the
script):

- It takes five real clips: 1080p and 720p (25 fps), 640×480 (25 fps), and two at 320×240
  (30 fps).
- For each clip it builds every variant: the containers, codecs, audio tracks, rotation tags,
  HDR, frame rates, interlacing, stretched pixels, odd sizes, cover art, a truncated file, a
  browser recording and a renamed text file.
- Each variant goes through the full pipeline and is compared with the original clip:
  - orientation, aspect ratio and frame count;
  - contact within 2 frames, and the trophy within 0.25 s;
  - result videos in H.264 with one frame per analysed frame.

The fast regression tests are `tests/test_video_formats.py` (every container and codec, AV1,
interlacing, stretched pixels) and `tests/test_phone_video.py` (a rotated iPhone HEVC
`.mov`). They need ffmpeg, so they run in CI and are skipped on machines without it.

## Results

Report: `evaluation/reports/formats_20261008-045155_63f0128-dirty.md`.

- **Runs:** 160, which is 32 variants of each of the five clips.
- **What the first run caught:** three bugs, all now fixed:
  - Interlaced video was analysed at half the frame rate, with combed motion.
  - Stretched-pixel video made the player 25% too thin.
  - A browser recording's frame count came back as −2.7 × 10¹⁷.
- **The final run:** 3 runs were flagged, and all three were mistakes in how the test built
  those files, not in the pipeline:
  - The variable-frame-rate clips were made on a coarse time base, which silently dropped
    frames.
  - The 60 fps contact tolerance didn't allow for 25 → 60 fps repeating frames unevenly.

  With both corrected, the reruns pass.
- **Contact:** across the 150 analysed variants it matched the original exactly in 68% of
  runs and within 1 frame in 95%. The two exceptions were the 60 fps case (passes once frame
  repetition is allowed for) and a truncated file, which now carries the "looks incomplete"
  warning.
- **Trophy:** it matched exactly in 54% of runs and within 1 frame in 79%, and never moved
  more than 6.2 frames (0.25 s).

## Known limits

- **HDR colour.** 10-bit HEVC, the iPhone default, decodes correctly. Genuine HDR footage (HLG
  or HDR10), though, is decoded without tone mapping, so it looks darker and flatter to the pose
  model.
  - In testing on synthetic HLG, the frames came out about 25% darker. Contact was unaffected,
    but the trophy moved up to 6 frames on one clip.
  - A tone-mapping step tuned on synthetic HDR didn't get closer to the original, so it wasn't
    added. It needs a few real iPhone HDR serves to tune.
- **The trophy is sensitive to re-encoding.** Any lossy re-compression (even plain H.264) can
  move it a few frames, up to 5 on a 320×240 clip, because the knee-bend peak is flat.
  Contact doesn't move.
- **Truncated MTS files** can't be detected as incomplete: the format's frame count comes from
  the data actually present.
