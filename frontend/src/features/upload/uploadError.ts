import { ApiError } from "../../api";

/**
 * How to describe a failed upload. The server's own message is shown for
 * anything it refused (a limit, a bad file); only network and server errors
 * get the "check your connection" advice, since retrying can fix those.
 */
export function uploadErrorText(error: Error): { title: string; detail: string } {
  if (error instanceof ApiError && error.status === 429) {
    return { title: "Limit reached.", detail: error.message };
  }
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
    return { title: "Upload failed.", detail: error.message };
  }
  return { title: "Upload failed.", detail: `${error.message} Check your connection and try again.` };
}
