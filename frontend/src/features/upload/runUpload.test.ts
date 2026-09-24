import { describe, expect, it, vi } from "vitest";

import { ApiError, UploadAbortedError, type ApiClient } from "../../api/client";
import type { AnalysisSummary } from "../../api/types";
import { runUpload, type UploadStep } from "./runUpload";

const summary = (status: AnalysisSummary["status"]): AnalysisSummary => ({
  id: "a1", hand: "right", status, filename: "serve.mp4",
  created_at: "2026-09-23T00:00:00Z", updated_at: "2026-09-23T00:00:00Z",
  error: null, thumbnail_url: null, counts: null,
});

function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    createAnalysis: vi.fn(async () => ({
      analysis: summary("awaiting_upload"),
      upload: { url: "/api/storage/x", method: "PUT" as const, headers: { "Content-Type": "video/mp4" }, expires_at: "" },
    })),
    uploadVideo: vi.fn(async (_t, _f, onProgress) => {
      onProgress(0.5);
      onProgress(1);
    }),
    startAnalysis: vi.fn(async () => summary("queued")),
    retryAnalysis: vi.fn(),
    getAnalysis: vi.fn(),
    listAnalyses: vi.fn(),
    getResult: vi.fn(),
    getFrames: vi.fn(),
    ...overrides,
  } as ApiClient;
}

const file = new File(["x".repeat(2048)], "serve.mp4", { type: "video/mp4" });

describe("runUpload", () => {
  it("creates, uploads with progress, then starts", async () => {
    const client = fakeClient();
    const steps: UploadStep[] = [];
    const progress: number[] = [];
    const result = await runUpload(client, { file, hand: "left", contentType: "video/mp4" }, {
      onStep: (s) => steps.push(s),
      onProgress: (p) => progress.push(p),
    });
    expect(steps).toEqual(["creating", "uploading", "starting"]);
    expect(progress).toEqual([0.5, 1]);
    expect(client.createAnalysis).toHaveBeenCalledWith({
      hand: "left", filename: "serve.mp4", content_type: "video/mp4", size_bytes: 2048,
    });
    expect(client.startAnalysis).toHaveBeenCalledWith("a1");
    expect(result.status).toBe("queued");
  });

  it("does not start the job if the upload fails", async () => {
    const client = fakeClient({
      uploadVideo: vi.fn(async () => {
        throw new ApiError(403, "Invalid or expired upload URL");
      }),
    });
    await expect(runUpload(client, { file, hand: "right", contentType: "video/mp4" })).rejects.toThrow("expired");
    expect(client.startAnalysis).not.toHaveBeenCalled();
  });

  it("stops when cancelled", async () => {
    const controller = new AbortController();
    const client = fakeClient({
      uploadVideo: vi.fn(async () => {
        controller.abort();
        throw new UploadAbortedError();
      }),
    });
    await expect(
      runUpload(client, { file, hand: "right", contentType: "video/mp4" }, { signal: controller.signal }),
    ).rejects.toBeInstanceOf(UploadAbortedError);
    expect(client.startAnalysis).not.toHaveBeenCalled();
  });
});
