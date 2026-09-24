/**
 * Frame i of the (constant frame rate) playback video is presented at i / fps.
 * The small epsilon absorbs floating-point error: 1.16 s * 25 fps is
 * 28.999999999999996, which must still be frame 29.
 */
const EPSILON = 1e-3;

export function clampFrame(frame: number, nFrames: number): number {
  return Math.min(Math.max(Math.trunc(frame), 0), Math.max(nFrames - 1, 0));
}

export function frameAtTime(seconds: number, fps: number, nFrames: number): number {
  return clampFrame(Math.floor(seconds * fps + EPSILON), nFrames);
}

/**
 * Seek target for a frame: its midpoint rather than its start, so decoder
 * rounding can't land on the previous frame.
 */
export function timeForFrame(frame: number, fps: number, nFrames: number): number {
  return (clampFrame(frame, nFrames) + 0.5) / fps;
}
