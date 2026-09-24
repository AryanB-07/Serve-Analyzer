import type { ErrorCode } from "../../api/types";

export interface ErrorCopy {
  title: string;
  advice: string;
  /** Whether re-running the same video could plausibly succeed. */
  retryHelps: boolean;
  /** Whether to show the server's own message (it has specifics like the clip length). */
  showDetail: boolean;
  linkGuide: boolean;
}

/** Record over every ErrorCode, so a new backend code fails type-checking until it has copy. */
export const ERROR_COPY: Record<ErrorCode, ErrorCopy> = {
  UNREADABLE_VIDEO: {
    title: "We couldn't read this video",
    advice: "Export it as an MP4 and upload it again.",
    retryHelps: false,
    showDetail: false,
    linkGuide: false,
  },
  VIDEO_TOO_LONG: {
    title: "This video is too long",
    advice: "Trim it to a single serve, 15 seconds at most.",
    retryHelps: false,
    showDetail: true,
    linkGuide: false,
  },
  FPS_TOO_LOW: {
    title: "The frame rate is too low",
    advice: "Record at 30 fps or higher; 60 fps is even better.",
    retryHelps: false,
    showDetail: true,
    linkGuide: true,
  },
  NO_PERSON_DETECTED: {
    title: "We couldn't detect a person clearly",
    advice: "Film side-on with your whole body in frame and good light.",
    retryHelps: false,
    showDetail: false,
    linkGuide: true,
  },
  INTERNAL: {
    title: "Something went wrong on our side",
    advice: "This wasn't caused by your video. Try again in a moment.",
    retryHelps: true,
    showDetail: false,
    linkGuide: false,
  },
};

/**
 * Copy for a code from the server. Falls back to INTERNAL for codes this build
 * doesn't know (a newer backend), rather than crashing the page.
 */
export function errorCopyFor(code: string | undefined): ErrorCopy {
  return (code && (ERROR_COPY as Record<string, ErrorCopy>)[code]) || ERROR_COPY.INTERNAL;
}
