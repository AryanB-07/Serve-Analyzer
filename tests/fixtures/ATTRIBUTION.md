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
