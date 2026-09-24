import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { AnalysisResult, FramesPayload } from "../../api/types";
import { canvasBackingSize, mediaRect, type Size } from "../../lib/coords";
import { phaseForSegment, segmentAt } from "../../lib/phases";
import { angleLabels, jointStatuses, metricStatuses, poseAt, type LandmarkSource } from "../../lib/skeleton";
import { usePlayheadStore } from "../../playhead/context";
import { useVideoClock } from "../../playhead/useVideoClock";
import { drawOverlay } from "./overlay/drawOverlay";

export interface OverlayOptions {
  showSkeleton: boolean;
  showLabels: boolean;
  source: LandmarkSource;
}

/**
 * Video with a canvas skeleton on top. The canvas is redrawn from a store
 * subscription, outside React's render cycle: playing the video re-renders
 * no React components here.
 */
export function VideoStage({
  result,
  frames,
  options,
  controls = false,
  muted = false,
  onVideoElement,
  onVideoClick,
}: {
  result: AnalysisResult;
  frames: FramesPayload;
  options: OverlayOptions;
  controls?: boolean;
  muted?: boolean;
  /** Receives the <video> element, e.g. to slave it to another playhead. */
  onVideoElement?: (video: HTMLVideoElement | null) => void;
  /** Overrides click-to-toggle-play (default: this stage's own playhead). */
  onVideoClick?: () => void;
}) {
  const store = usePlayheadStore();
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const optionsRef = useRef(options);
  const drawRef = useRef<() => void>(() => {});

  useVideoClock(video, store);

  useEffect(() => {
    onVideoElement?.(video);
  }, [video, onVideoElement]);

  useLayoutEffect(() => {
    optionsRef.current = options;
    drawRef.current();
  }, [options]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let size: Size = { width: 0, height: 0 };
    const media = { width: frames.width, height: frames.height };

    const draw = () => {
      const { frame } = store.getState();
      const opts = optionsRef.current;
      const phase = phaseForSegment(segmentAt(frame, result.phases));
      const pose = poseAt(frames, frame, opts.source);
      drawOverlay(ctx, {
        size,
        rect: mediaRect(size, media, "contain"),
        pose,
        jointStatus: jointStatuses(result.labels, phase, result.hand),
        labels: opts.showLabels ? angleLabels(frames, frame, result.hand, pose) : [],
        labelStatus: metricStatuses(result.labels, phase),
        showSkeleton: opts.showSkeleton,
        showLabels: opts.showLabels,
      });
    };
    drawRef.current = draw;

    const resize = new ResizeObserver(([entry]) => {
      if (!entry) return;
      size = { width: entry.contentRect.width, height: entry.contentRect.height };
      if (size.width === 0 || size.height === 0) return;
      const backing = canvasBackingSize(size, window.devicePixelRatio);
      canvas.width = backing.width;
      canvas.height = backing.height;
      ctx.setTransform(backing.width / size.width, 0, 0, backing.height / size.height, 0, 0);
      draw();
    });
    resize.observe(canvas);
    const unsubscribe = store.subscribe(draw);
    return () => {
      resize.disconnect();
      unsubscribe();
      drawRef.current = () => {};
    };
  }, [store, frames, result]);

  return (
    <div
      className="relative w-full max-h-[min(60vh,720px)] overflow-hidden rounded-xl bg-black"
      style={{ aspectRatio: `${frames.width} / ${frames.height}` }}
    >
      <video
        ref={setVideo}
        src={result.video_url}
        className="absolute inset-0 h-full w-full object-contain"
        playsInline
        preload="auto"
        controls={controls}
        muted={muted}
        onClick={controls ? undefined : (onVideoClick ?? store.togglePlay)}
        aria-label="Serve video"
      />
      <canvas
        ref={canvasRef}
        className="pointer-events-none absolute inset-0 h-full w-full"
        aria-hidden
        data-testid="skeleton-canvas"
      />
    </div>
  );
}
