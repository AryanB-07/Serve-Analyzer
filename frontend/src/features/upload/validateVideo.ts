import type { CreateAnalysisRequest } from "../../api/types";

type UploadContentType = CreateAnalysisRequest["content_type"];

/** Mirrors the backend limits (serve_api Settings and the pipeline config). */
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;
export const MAX_DURATION_S = 15;

/**
 * Supported files by extension. The extension decides the type sent to the server, because
 * browsers report these inconsistently (empty for .mov or .mkv on some systems, "model/vnd.mts"
 * for .mts). Must match serve_api/schemas.py UploadContentType.
 */
const BY_EXTENSION: Record<string, UploadContentType> = {
  mp4: "video/mp4", m4v: "video/mp4",
  mov: "video/quicktime", qt: "video/quicktime",
  webm: "video/webm",
  mkv: "video/x-matroska",
  avi: "video/x-msvideo",
  "3gp": "video/3gpp",
  mts: "video/mp2t", m2ts: "video/mp2t", ts: "video/mp2t",
};
/** Fallback for files without a recognised extension. */
const BY_MIME: Record<string, UploadContentType> = {
  "video/mp4": "video/mp4", "video/x-m4v": "video/mp4",
  "video/quicktime": "video/quicktime",
  "video/webm": "video/webm",
  "video/x-matroska": "video/x-matroska", "video/mkv": "video/x-matroska",
  "video/x-msvideo": "video/x-msvideo", "video/avi": "video/x-msvideo", "video/msvideo": "video/x-msvideo",
  "video/3gpp": "video/3gpp",
  "video/mp2t": "video/mp2t", "model/vnd.mts": "video/mp2t", "video/vnd.dlna.mpeg-tts": "video/mp2t",
};

/** For the file picker's accept attribute: any video, plus the extensions some systems don't tag as video. */
export const ACCEPT = ["video/*", ...Object.keys(BY_EXTENSION).map((e) => `.${e}`)].join(",");
export const FORMATS_LABEL = "MP4, MOV, WebM, MKV, AVI, 3GP or MTS";

export interface VideoMetadata {
  durationS: number;
  width: number;
  height: number;
}

export type Check =
  | { ok: true; contentType: UploadContentType }
  | { ok: false; message: string };

/**
 * Type and size checks. The extension decides the type; the browser's MIME type is the
 * fallback for files without a known extension.
 */
export function checkFile(file: Pick<File, "name" | "type" | "size">): Check {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const contentType = BY_EXTENSION[extension] ?? BY_MIME[file.type.toLowerCase()];
  if (!contentType) {
    return { ok: false, message: `That file type isn't supported. Choose a video (${FORMATS_LABEL}).` };
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
  if (meta === null) return null;
  if (meta.width === 0 && meta.height === 0) return "This file has no video in it (only audio).";
  if (!Number.isFinite(meta.durationS)) return null;
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
