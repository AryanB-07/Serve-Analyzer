import { ApiError } from "./client";

/**
 * Retry once for network errors and 5xx; never for 4xx (not found, conflict),
 * where asking again only delays showing the real answer.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}
