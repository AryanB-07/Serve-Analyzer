import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { api, UploadAbortedError } from "../../api";
import { queryKeys } from "../../api/queries";
import { runUpload, type UploadRequest, type UploadStep } from "./runUpload";

export interface UploadProgress {
  step: UploadStep;
  fraction: number;
}

/** Runs the upload flow as a TanStack mutation, tracking step and byte progress. */
export function useUploadAnalysis() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const controller = useRef<AbortController | null>(null);
  const [progress, setProgress] = useState<UploadProgress>({ step: "creating", fraction: 0 });

  useEffect(() => () => controller.current?.abort(), []);

  const mutation = useMutation({
    mutationFn: (request: UploadRequest) => {
      controller.current = new AbortController();
      setProgress({ step: "creating", fraction: 0 });
      return runUpload(api, request, {
        signal: controller.current.signal,
        onStep: (step) => setProgress((p) => ({ ...p, step })),
        onProgress: (fraction) => setProgress((p) => ({ ...p, fraction })),
      });
    },
    onSuccess: (summary) => {
      queryClient.setQueryData(queryKeys.analysis(summary.id), summary);
      void queryClient.invalidateQueries({ queryKey: queryKeys.analyses });
      navigate(`/analyses/${summary.id}`);
    },
  });

  const cancelled = mutation.error instanceof UploadAbortedError;
  return {
    upload: mutation.mutate,
    cancel: () => controller.current?.abort(),
    reset: mutation.reset,
    isUploading: mutation.isPending,
    progress,
    error: cancelled ? null : mutation.error,
    cancelled,
  };
}
