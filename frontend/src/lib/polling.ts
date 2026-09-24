import type { AnalysisStatus } from "../api/types";

export const TERMINAL_STATUSES: ReadonlySet<AnalysisStatus> = new Set(["succeeded", "failed"]);

export const POLL_INITIAL_MS = 1000;
export const POLL_FACTOR = 1.5;
export const POLL_MAX_MS = 5000;

/** Exponential backoff for status polling: 1s, 1.5s, 2.25s, ... capped at 5s. */
export function nextPollDelay(attempt: number): number {
  return Math.min(POLL_INITIAL_MS * POLL_FACTOR ** Math.max(0, attempt), POLL_MAX_MS);
}

export function isTerminal(status: AnalysisStatus | undefined): boolean {
  return status !== undefined && TERMINAL_STATUSES.has(status);
}

/**
 * Tracks polls since the status last changed. A stage transition means work
 * is progressing, so polling returns to the fast end of the backoff; it only
 * slows down while the status sits still.
 */
export function createStatusBackoff() {
  let lastStatus: AnalysisStatus | undefined;
  let pollsAtChange = 0;
  return (status: AnalysisStatus | undefined, pollCount: number): number | false => {
    if (isTerminal(status)) return false;
    if (status !== lastStatus) {
      lastStatus = status;
      pollsAtChange = pollCount;
    }
    return nextPollDelay(pollCount - pollsAtChange);
  };
}
