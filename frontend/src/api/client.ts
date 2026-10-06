import type {
  AnalysisList,
  AnalysisResult,
  AnalysisSummary,
  CreateAnalysisRequest,
  CreateAnalysisResponse,
  Credentials,
  FramesPayload,
  SignupRequest,
  UploadTarget,
  User,
} from "./types";

/** Everything the UI needs from the backend. Implemented over HTTP and by the mock. */
export interface ApiClient {
  /** The signed-in user, or null when there is no valid session. */
  getMe(): Promise<User | null>;
  signUp(body: SignupRequest): Promise<User>;
  logIn(body: Credentials): Promise<User>;
  logOut(): Promise<void>;
  /** Confirm an email address with the token from the emailed link. */
  verifyEmail(token: string): Promise<void>;
  resendVerification(): Promise<void>;
  /** Always resolves (the server answers the same whether or not the address has an account). */
  requestPasswordReset(email: string): Promise<void>;
  resetPassword(token: string, password: string): Promise<void>;
  /** Permanently delete the signed-in account and everything in it. */
  deleteAccount(password: string): Promise<void>;
  deleteAnalysis(id: string): Promise<void>;
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

let onUnauthorized: () => void = () => {};

/**
 * Called when a data request is refused with 401, i.e. the session has expired
 * or been revoked. (A 401 from the auth endpoints themselves means a wrong
 * password or no session yet, and is left to the caller.)
 */
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (res.status === 401 && !path.startsWith("/auth/")) onUnauthorized();
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
  if (res.status === 204) return undefined as T;
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
  getMe: async () => {
    try {
      return await request<User>("/auth/me");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
  signUp: (body) => request("/auth/signup", { method: "POST", body: JSON.stringify(body) }),
  logIn: (body) => request("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  logOut: () => request("/auth/logout", { method: "POST" }),
  verifyEmail: (token) => request("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) }),
  resendVerification: () => request("/auth/verify-email/resend", { method: "POST" }),
  requestPasswordReset: (email) =>
    request("/auth/password-reset", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token, password) =>
    request("/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ token, password }) }),
  deleteAccount: (password) => request("/auth/me", { method: "DELETE", body: JSON.stringify({ password }) }),
  deleteAnalysis: (id) => request(`/analyses/${encodeURIComponent(id)}`, { method: "DELETE" }),
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
