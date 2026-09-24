import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router";

import { USE_MOCKS } from "../../api";
import { DEMO_IDS } from "../../api/demo";
import type { Hand } from "../../api/types";
import { Dropzone } from "./Dropzone";
import { FilmingGuide } from "./FilmingGuide";
import { HandSelector } from "./HandSelector";
import { useUploadAnalysis, type UploadProgress } from "./useUploadAnalysis";
import { checkFile, checkMetadata, readVideoMetadata, type VideoMetadata } from "./validateVideo";

interface Selected {
  file: File;
  contentType: "video/mp4" | "video/quicktime";
  meta: VideoMetadata | null;
  previewUrl: string;
}

function formatBytes(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

function SelectedFile({ selected, onClear, disabled }: { selected: Selected; onClear: () => void; disabled: boolean }) {
  const { file, meta, previewUrl } = selected;
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border bg-surface p-3">
      <video src={previewUrl} muted playsInline preload="metadata" className="h-16 w-24 shrink-0 rounded-md bg-black object-contain" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium" title={file.name}>{file.name}</p>
        <p className="tabular text-sm text-ink-muted">
          {formatBytes(file.size)}
          {meta && Number.isFinite(meta.durationS) && ` · ${meta.durationS.toFixed(1)} s · ${meta.width}×${meta.height}`}
        </p>
        {!meta && <p className="text-sm text-ink-muted">We couldn't preview this file here; the server will check it.</p>}
      </div>
      <button
        type="button"
        onClick={onClear}
        disabled={disabled}
        className="rounded-lg px-2 py-1 text-sm text-ink-muted hover:text-ink disabled:opacity-50"
      >
        Change
      </button>
    </div>
  );
}

const STEP_TEXT: Record<UploadProgress["step"], string> = {
  creating: "Preparing upload…",
  uploading: "Uploading",
  starting: "Starting analysis…",
};

function UploadProgressBar({ progress, size, onCancel }: { progress: UploadProgress; size: number; onCancel: () => void }) {
  const pct = Math.round(progress.fraction * 100);
  return (
    <div className="space-y-2 rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{STEP_TEXT[progress.step]}</span>
        <span className="tabular text-ink-muted">
          {formatBytes(progress.fraction * size)} of {formatBytes(size)} · {pct}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-label="Upload progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <div className="h-full rounded-full bg-accent transition-[width] duration-200" style={{ width: `${pct}%` }} />
      </div>
      {progress.step !== "starting" && (
        <button type="button" onClick={onCancel} className="text-sm font-medium text-ink-muted hover:text-ink">
          Cancel upload
        </button>
      )}
    </div>
  );
}

export function UploadPage() {
  const [hand, setHand] = useState<Hand | null>(null);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [checking, setChecking] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const { upload, cancel, reset, isUploading, progress, error, cancelled } = useUploadAnalysis();
  const location = useLocation();
  const latestPick = useRef(0);

  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  }, [location.hash]);

  useEffect(() => () => {
    if (selected) URL.revokeObjectURL(selected.previewUrl);
  }, [selected]);

  async function onFile(file: File) {
    const pick = ++latestPick.current;
    reset();
    setFileError(null);
    setSelected(null);
    const basic = checkFile(file);
    if (!basic.ok) return setFileError(basic.message);
    setChecking(true);
    const meta = await readVideoMetadata(file);
    if (pick !== latestPick.current) return; // a newer file was chosen meanwhile
    setChecking(false);
    const problem = checkMetadata(meta);
    if (problem) return setFileError(problem);
    setSelected({ file, contentType: basic.contentType, meta, previewUrl: URL.createObjectURL(file) });
  }

  const canSubmit = selected !== null && hand !== null && !isUploading;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_26rem]">
      <div className="space-y-6">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">Analyze your serve</h1>
          <p className="text-ink-muted">
            Upload a side-on video of one serve. You'll get your skeleton tracked frame by frame, joint angles at each
            phase, and feedback on what to work on.{" "}
            <a href="#filming-guide" className="text-accent underline lg:hidden">How to film it</a>
          </p>
        </header>

        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (selected && hand) upload({ file: selected.file, hand, contentType: selected.contentType });
          }}
        >
          <HandSelector value={hand} onChange={setHand} disabled={isUploading} />

          <div className="space-y-2">
            <p className="text-sm font-medium" id="video-label">Your video</p>
            {selected ? (
              <SelectedFile selected={selected} onClear={() => setSelected(null)} disabled={isUploading} />
            ) : (
              <Dropzone onFile={onFile} disabled={checking} />
            )}
            {checking && <p className="text-sm text-ink-muted" role="status">Checking video…</p>}
            {fileError && (
              <p role="alert" className="text-sm font-medium text-bad">
                {fileError}
              </p>
            )}
          </div>

          {isUploading && selected && <UploadProgressBar progress={progress} size={selected.file.size} onCancel={cancel} />}
          {error && (
            <p role="alert" className="rounded-lg border border-bad/40 bg-surface p-3 text-sm">
              <span className="font-medium text-bad">Upload failed.</span> {error.message} Check your connection and try again.
            </p>
          )}
          {cancelled && <p role="status" className="text-sm text-ink-muted">Upload cancelled.</p>}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded-lg bg-accent px-5 py-2.5 font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isUploading ? "Uploading…" : "Analyze serve"}
            </button>
            {!hand && selected && <span className="text-sm text-ink-muted">Choose your serving hand to continue.</span>}
            {USE_MOCKS && !isUploading && (
              <Link to={`/analyses/${DEMO_IDS[0]}`} className="text-sm font-medium text-accent hover:underline">
                Or open the demo analysis
              </Link>
            )}
          </div>
        </form>
      </div>

      <FilmingGuide />
    </div>
  );
}
