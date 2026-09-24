import { useEffect } from "react";

import { mapFrame, mapTime, slopeAt, type Anchor, type ClipTiming } from "../lib/align";
import { timeForFrame } from "../lib/time";
import type { PlayheadStore } from "./store";

const MAX_DRIFT_FRAMES = 1.5;

/**
 * Keeps a second video in step with a master playhead through a time warp.
 *
 * While the master plays, the follower plays too, at the master's rate times
 * the warp slope for the current segment, and is only re-seeked when it
 * drifts more than ~1.5 frames: seeking every frame would stutter. While
 * paused, it seeks to the exact mapped frame. Where the master shows a moment
 * the follower's clip doesn't contain, the follower holds its nearest frame.
 */
export function useFollowerVideo(
  video: HTMLVideoElement | null,
  master: PlayheadStore,
  leader: ClipTiming,
  follower: ClipTiming,
  anchors: Anchor[],
): void {
  useEffect(() => {
    if (!video) return;
    const sync = () => {
      const { frame, playing, rate } = master.getState();
      const { frame: target, outside } = mapFrame(frame, leader, follower, anchors);
      if (playing && !outside) {
        const tA = frame / leader.fps;
        video.playbackRate = Math.min(16, Math.max(0.0625, rate * slopeAt(tA, anchors)));
        const expected = mapTime(tA, anchors);
        if (Math.abs(video.currentTime - expected) > MAX_DRIFT_FRAMES / follower.fps) {
          video.currentTime = expected;
        }
        if (video.paused) video.play().catch(() => {});
      } else {
        if (!video.paused) video.pause();
        const exact = timeForFrame(target, follower.fps, follower.nFrames);
        if (Math.abs(video.currentTime - exact) > 0.25 / follower.fps) video.currentTime = exact;
      }
    };
    sync();
    return master.subscribe(sync);
  }, [video, master, leader, follower, anchors]);
}
