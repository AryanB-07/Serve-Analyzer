# Test fixture attribution

`sample_serve.mp4` is re-encoded (H.264, unmodified frames) from
[Intention-understanding-over-T-a-neuroimaging-study-on-shared-representations-and-tennis-return-Movie1.ogv](https://commons.wikimedia.org/wiki/File:Intention-understanding-over-T-a-neuroimaging-study-on-shared-representations-and-tennis-return-Movie1.ogv),
Movie 1 from Cacioppo S, Fontang F, Patel N, Decety J, Monteleone G, Cacioppo J (2014),
"Intention understanding over T: a neuroimaging study on shared representations and tennis
return predictions", *Frontiers in Human Neuroscience*, doi:10.3389/fnhum.2014.00781,
licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Notes for tests:

- 640x480, 25 fps, 125 frames (5 s).
- Filmed from across the net, not side-on, so metric values are not representative.
- The net occludes the lower legs for much of the clip.
- Right-handed player facing the camera. The clip ends at ball contact (last frame).
- MediaPipe reports the hitting elbow with low visibility throughout, so the racket drop
  phase is not detected with default settings.

`standing_still.mp4` is the first frame of `sample_serve.mp4` held for 3 s (75 frames at
25 fps, H.264), under the same licence. The player never swings, so the pipeline rejects it
with `NOT_A_SERVE`; the browser end-to-end test (`frontend/e2e`) uploads it to reach that
screen. Rebuild it with:

    ffmpeg -i sample_serve.mp4 -vf "select=eq(n\,0),loop=loop=74:size=1:start=0,setpts=N/25/TB" \
      -r 25 -frames:v 75 -an -c:v libx264 -preset veryslow -crf 28 -pix_fmt yuv420p \
      -movflags +faststart standing_still.mp4
