# Test fixture attribution

`sample_serve.mp4` is re-encoded (H.264, unmodified frames) from
[Intention-understanding-over-T-a-neuroimaging-study-on-shared-representations-and-tennis-return-Movie1.ogv](https://commons.wikimedia.org/wiki/File:Intention-understanding-over-T-a-neuroimaging-study-on-shared-representations-and-tennis-return-Movie1.ogv),
supplementary material from Wright et al., "Intention understanding over T: a neuroimaging study
on shared representations and tennis return predictions", *Frontiers in Human Neuroscience*,
licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Notes for tests:

- 640x480, 25 fps, 125 frames (5 s).
- Filmed from across the net, not side-on, so metric values are not representative.
- The net occludes the lower legs for much of the clip.
- MediaPipe labels the racket arm as the player's LEFT (the clip appears mirrored or the
  facing direction is misread), so the pipeline is run with `--hand left`.
