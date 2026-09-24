import { useEffect } from "react";

import { frameAtTime, timeForFrame } from "../lib/time";
import type { PlayheadStore } from "./store";

/**
 * Binds a <video> element to the playhead store: the video is the clock
 * while playing, and store commands (seek/play/pause/rate) drive the video.
 */
export function useVideoClock(video: HTMLVideoElement | null, store: PlayheadStore): void {
  useEffect(() => {
    if (!video) return;
    const { fps, nFrames } = store;
    const report = (seconds: number) => store.reportFrame(frameAtTime(seconds, fps, nFrames));
    let stopped = false;
    let frameHandle = 0;
    let rafHandle = 0;

    // Typed as always present, but missing in older Firefox.
    const supportsFrameCallback =
      typeof (video as Partial<HTMLVideoElement>).requestVideoFrameCallback === "function";
    if (supportsFrameCallback) {
      // Fires once per frame actually presented (including after a seek while
      // paused), with that frame's exact media timestamp.
      const onFrame: VideoFrameRequestCallback = (_now, metadata) => {
        if (stopped) return;
        report(metadata.mediaTime);
        frameHandle = video.requestVideoFrameCallback(onFrame);
      };
      frameHandle = video.requestVideoFrameCallback(onFrame);
    } else {
      const tick = () => {
        if (stopped) return;
        if (!video.paused) report(video.currentTime);
        rafHandle = requestAnimationFrame(tick);
      };
      rafHandle = requestAnimationFrame(tick);
    }

    const onSeeked = () => {
      if (!supportsFrameCallback) report(video.currentTime);
    };
    const onPlay = () => store.reportPlaying(true);
    const onPause = () => store.reportPlaying(false);
    const onRate = () => store.reportRate(video.playbackRate);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("ended", onPause);
    video.addEventListener("ratechange", onRate);

    const offCommand = store.onCommand((command) => {
      switch (command.type) {
        case "seek":
          video.currentTime = timeForFrame(command.frame, fps, nFrames);
          break;
        case "play":
          // Rejects if interrupted by a pause; the pause event keeps state right.
          video.play().catch(() => {});
          break;
        case "pause":
          video.pause();
          break;
        case "rate":
          video.playbackRate = command.rate;
          break;
      }
    });

    return () => {
      stopped = true;
      if (supportsFrameCallback) video.cancelVideoFrameCallback(frameHandle);
      cancelAnimationFrame(rafHandle);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("ended", onPause);
      video.removeEventListener("ratechange", onRate);
      offCommand();
    };
  }, [video, store]);
}
