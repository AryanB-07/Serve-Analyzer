import { useCallback, useState } from "react";

/** The results page's two views: scores in plain words, or the exact angles with their confidence. */
export type ResultsMode = "simple" | "advanced";

export const MODE_KEY = "serve-analyzer:results-mode";

function read(): ResultsMode {
  try {
    return window.localStorage.getItem(MODE_KEY) === "advanced" ? "advanced" : "simple";
  } catch {
    return "simple"; // storage blocked: simple, and the choice lasts for this page only
  }
}

/** Remembered per browser: whoever uses this device sees the view they last chose. */
export function useResultsMode(): [ResultsMode, (mode: ResultsMode) => void] {
  const [mode, setMode] = useState<ResultsMode>(read);
  const change = useCallback((next: ResultsMode) => {
    setMode(next);
    try {
      window.localStorage.setItem(MODE_KEY, next);
    } catch {
      // Not saved; it still applies until the page is left.
    }
  }, []);
  return [mode, change];
}
