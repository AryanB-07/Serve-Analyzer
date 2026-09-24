import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { createStatusBackoff } from "../lib/polling";
import { api } from ".";

export const queryKeys = {
  analyses: ["analyses"] as const,
  analysis: (id: string) => ["analysis", id] as const,
  result: (id: string) => ["result", id] as const,
  frames: (id: string) => ["frames", id] as const,
};

/**
 * Status of one analysis. Polls until it succeeds or fails, backing off while
 * the status is unchanged and speeding up again on each stage transition.
 */
export function useAnalysis(id: string) {
  const [backoff] = useState(createStatusBackoff);
  return useQuery({
    queryKey: queryKeys.analysis(id),
    queryFn: () => api.getAnalysis(id),
    refetchInterval: (query) => backoff(query.state.data?.status, query.state.dataUpdateCount),
  });
}

/** Results and frames never change once written, so they are cached for the session. */
export function useResult(id: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.result(id),
    queryFn: () => api.getResult(id),
    enabled,
    staleTime: Infinity,
  });
}

export function useFrames(id: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.frames(id),
    queryFn: () => api.getFrames(id),
    enabled,
    staleTime: Infinity,
  });
}

export function useAnalyses() {
  return useQuery({ queryKey: queryKeys.analyses, queryFn: () => api.listAnalyses() });
}
