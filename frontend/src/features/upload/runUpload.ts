import type { ApiClient } from "../../api/client";
import type { AnalysisSummary, CreateAnalysisRequest, Hand } from "../../api/types";

export type UploadStep = "creating" | "uploading" | "starting";

export interface UploadRequest {
  file: File;
  hand: Hand;
  contentType: CreateAnalysisRequest["content_type"];
}

export interface UploadCallbacks {
  onStep?: (step: UploadStep) => void;
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

/**
 * The browser side of the presigned-upload flow:
 *   1. POST /analyses            -> record + signed PUT URL
 *   2. PUT the file to that URL  -> straight to storage, with progress
 *   3. POST /analyses/{id}/start -> queue the job
 * The API client is a parameter so the flow can be tested with a fake.
 */
export async function runUpload(
  client: ApiClient,
  { file, hand, contentType }: UploadRequest,
  { onStep, onProgress, signal }: UploadCallbacks = {},
): Promise<AnalysisSummary> {
  onStep?.("creating");
  const { analysis, upload } = await client.createAnalysis({
    hand,
    filename: file.name,
    content_type: contentType,
    size_bytes: file.size,
  });
  signal?.throwIfAborted();

  onStep?.("uploading");
  await client.uploadVideo(upload, file, (f) => onProgress?.(f), signal);
  signal?.throwIfAborted();

  onStep?.("starting");
  return client.startAnalysis(analysis.id);
}
