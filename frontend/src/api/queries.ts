import { useQuery } from "@tanstack/react-query";

import { isTerminal, nextPollDelay } from "../lib/polling";
import { api } from ".";

export const queryKeys = {
  analyses: ["analyses"] as const,
  analysis: (id: string) => ["analysis", id] as const,
  result: (id: string) => ["result", id] as const,
  frames: (id: string) => ["frames", id] as const,
};

/** Status of one analysis; polls with backoff until it succeeds or fails. */
export function useAnalysis(id: string) {
  return useQuery({
    queryKey: queryKeys.analysis(id),
    queryFn: () => api.getAnalysis(id),
    refetchInterval: (query) =>
      isTerminal(query.state.data?.status) ? false : nextPollDelay(query.state.dataUpdateCount),
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
