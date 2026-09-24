import type {
  AnalysisList,
  AnalysisResult,
  AnalysisSummary,
  CreateAnalysisRequest,
  CreateAnalysisResponse,
  FramesPayload,
  UploadTarget,
} from "./types";

/** Everything the UI needs from the backend. Implemented over HTTP and by the mock. */
export interface ApiClient {
  createAnalysis(body: CreateAnalysisRequest): Promise<CreateAnalysisResponse>;
  uploadVideo(
    target: UploadTarget,
    file: Blob,
    onProgress: (fraction: number) => void,
    signal?: AbortSignal,
  ): Promise<void>;
  startAnalysis(id: string): Promise<AnalysisSummary>;
  retryAnalysis(id: string): Promise<AnalysisSummary>;
  getAnalysis(id: string): Promise<AnalysisSummary>;
  listAnalyses(cursor?: string): Promise<AnalysisList>;
  getResult(id: string): Promise<AnalysisResult>;
  getFrames(id: string): Promise<FramesPayload>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class UploadAbortedError extends Error {
  constructor() {
    super("Upload cancelled");
    this.name = "UploadAbortedError";
  }
}

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body: keep the status text.
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** fetch() cannot report upload progress, so the PUT uses XMLHttpRequest. */
export function putWithProgress(
  target: UploadTarget,
  file: Blob,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new UploadAbortedError());
    const xhr = new XMLHttpRequest();
    xhr.open(target.method, target.url);
    for (const [name, value] of Object.entries(target.headers)) xhr.setRequestHeader(name, value);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(1);
        resolve();
      } else {
        reject(new ApiError(xhr.status, `Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.onabort = () => reject(new UploadAbortedError());
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(file);
  });
}

export const httpClient: ApiClient = {
  createAnalysis: (body) => request("/analyses", { method: "POST", body: JSON.stringify(body) }),
  uploadVideo: putWithProgress,
  startAnalysis: (id) => request(`/analyses/${encodeURIComponent(id)}/start`, { method: "POST" }),
  retryAnalysis: (id) => request(`/analyses/${encodeURIComponent(id)}/retry`, { method: "POST" }),
  getAnalysis: (id) => request(`/analyses/${encodeURIComponent(id)}`),
  listAnalyses: (cursor) =>
    request(`/analyses${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`),
  getResult: (id) => request(`/analyses/${encodeURIComponent(id)}/result`),
  getFrames: (id) => request(`/analyses/${encodeURIComponent(id)}/frames`),
};
