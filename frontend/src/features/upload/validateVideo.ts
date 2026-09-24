import type { CreateAnalysisRequest } from "../../api/types";

type UploadContentType = CreateAnalysisRequest["content_type"];

/** Mirrors the backend limits (serve_api Settings and the pipeline config). */
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;
export const MAX_DURATION_S = 15;

const BY_EXTENSION: Record<string, UploadContentType> = { mp4: "video/mp4", m4v: "video/mp4", mov: "video/quicktime" };
const BY_MIME: Record<string, UploadContentType> = { "video/mp4": "video/mp4", "video/quicktime": "video/quicktime" };

export interface VideoMetadata {
  durationS: number;
  width: number;
  height: number;
}

export type Check =
  | { ok: true; contentType: UploadContentType }
  | { ok: false; message: string };

/**
 * Type and size checks. Some browsers report an empty MIME type for .mov,
 * so the file extension is the fallback.
 */
export function checkFile(file: Pick<File, "name" | "type" | "size">): Check {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const contentType = BY_MIME[file.type] ?? BY_EXTENSION[extension];
  if (!contentType) {
    return { ok: false, message: "Please choose an MP4 or MOV video." };
  }
  if (file.size === 0) {
    return { ok: false, message: "That file is empty." };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    const mb = Math.round(file.size / (1024 * 1024));
    return { ok: false, message: `That file is ${mb} MB; the limit is ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB. Trim it to one serve.` };
  }
  return { ok: true, contentType };
}

/** Duration check; null metadata (browser can't read the file) is allowed through. */
export function checkMetadata(meta: VideoMetadata | null): string | null {
  if (meta === null || !Number.isFinite(meta.durationS)) return null;
  if (meta.durationS > MAX_DURATION_S) {
    return `This video is ${meta.durationS.toFixed(1)} s long; the limit is ${MAX_DURATION_S} s. Trim it to a single serve.`;
  }
  if (meta.durationS < 0.5) return "This video is too short to contain a serve.";
  return null;
}

/**
 * Read duration and size from the file's metadata without uploading it.
 * Resolves null if the browser can't parse it (e.g. HEVC in some browsers).
 */
export function readVideoMetadata(file: Blob, timeoutMs = 8000): Promise<VideoMetadata | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    let settled = false;
    const finish = (meta: VideoMetadata | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      video.removeAttribute("src");
      video.load();
      URL.revokeObjectURL(url);
      resolve(meta);
    };
    const timer = setTimeout(() => finish(null), timeoutMs);
    video.preload = "metadata";
    video.muted = true;
    video.onloadedmetadata = () =>
      finish({ durationS: video.duration, width: video.videoWidth, height: video.videoHeight });
    video.onerror = () => finish(null);
    video.src = url;
  });
}
