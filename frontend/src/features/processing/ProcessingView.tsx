import { useEffect, useState } from "react";
import { Link } from "react-router";

import type { AnalysisStatus, AnalysisSummary } from "../../api/types";
import { errorCopyFor } from "./errorCopy";

export const STAGES: { status: AnalysisStatus; label: string; detail: string }[] = [
  { status: "queued", label: "Queued", detail: "Waiting for a worker" },
  { status: "extracting_pose", label: "Tracking your body", detail: "Finding joints in every frame" },
  { status: "analyzing", label: "Analyzing", detail: "Angles, phases and feedback" },
  { status: "rendering", label: "Preparing video", detail: "Encoding for playback" },
];

export type StageState = "done" | "current" | "upcoming";

export function stageStates(status: AnalysisStatus): StageState[] {
  const current = STAGES.findIndex((s) => s.status === status);
  if (status === "succeeded") return STAGES.map(() => "done");
  return STAGES.map((_, i) => (current === -1 ? "upcoming" : i < current ? "done" : i === current ? "current" : "upcoming"));
}

function useElapsedSeconds(since: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return Math.max(0, Math.floor((now - since) / 1000));
}

function StageIcon({ state }: { state: StageState }) {
  if (state === "done") {
    return (
      <svg viewBox="0 0 20 20" className="size-5 text-good" aria-hidden>
        <circle cx="10" cy="10" r="9" fill="currentColor" />
        <path d="m6 10.5 2.5 2.5L14 7.5" fill="none" stroke="var(--bg)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (state === "current") {
    return (
      <svg viewBox="0 0 20 20" className="size-5 animate-spin text-accent motion-reduce:animate-none" aria-hidden>
        <circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
        <path d="M10 2a8 8 0 0 1 8 8" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
    );
  }
  return <span className="block size-5 rounded-full border-2 border-border" aria-hidden />;
}

const STATE_TEXT: Record<StageState, string> = { done: "done", current: "in progress", upcoming: "not started" };

function Stages({ summary, since }: { summary: AnalysisSummary; since: number }) {
  const elapsed = useElapsedSeconds(since);
  const states = stageStates(summary.status);
  const current = STAGES.find((s) => s.status === summary.status);
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Analyzing your serve</h1>
        <p className="text-ink-muted">
          {summary.filename} · <span className="tabular">{elapsed}s</span> elapsed. This usually takes under a minute.
        </p>
      </div>
      <p className="sr-only" role="status" aria-live="polite">
        {current ? `${current.label}: ${current.detail}` : ""}
      </p>
      <ol className="space-y-3">
        {STAGES.map((stage, i) => (
          <li key={stage.status} className="flex items-start gap-3" data-state={states[i]}>
            <StageIcon state={states[i]!} />
            <div>
              <p className={`font-medium ${states[i] === "upcoming" ? "text-ink-muted" : ""}`}>
                {stage.label}
                <span className="sr-only"> ({STATE_TEXT[states[i]!]})</span>
              </p>
              {states[i] === "current" && <p className="text-sm text-ink-muted">{stage.detail}</p>}
            </div>
          </li>
        ))}
      </ol>
      <p className="text-sm text-ink-muted">
        You can leave this page; the result will be in your <Link to="/history" className="text-accent underline">history</Link>.
      </p>
    </div>
  );
}

function Failed({
  summary,
  onRetry,
  retrying,
  retryError,
}: {
  summary: AnalysisSummary;
  onRetry: () => void;
  retrying: boolean;
  retryError: string | null;
}) {
  const copy = errorCopyFor(summary.error?.code);
  const primary = "rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50";
  const secondary = "rounded-lg border border-border px-4 py-2 font-medium hover:bg-surface-2 disabled:opacity-50";
  return (
    <div role="alert" className="space-y-4">
      <div className="flex items-start gap-3">
        <svg viewBox="0 0 24 24" className="mt-1 size-6 shrink-0 text-bad" aria-hidden>
          <path d="M12 2 1 21h22Z" fill="currentColor" />
          <path d="M12 9v5m0 3.2v.3" stroke="var(--bg)" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{copy.title}</h1>
          {copy.showDetail && summary.error?.message && <p>{summary.error.message}</p>}
          <p className="text-ink-muted">{copy.advice}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/" className={copy.retryHelps ? secondary : primary}>
          Upload a different video
        </Link>
        <button type="button" onClick={onRetry} disabled={retrying} className={copy.retryHelps ? primary : secondary}>
          {retrying ? "Retrying…" : "Try again"}
        </button>
        {copy.linkGuide && (
          <Link to="/#filming-guide" className="text-sm font-medium text-accent hover:underline">
            Read the filming guide
          </Link>
        )}
      </div>
      {retryError && <p className="text-sm text-bad">Couldn't retry: {retryError}</p>}
    </div>
  );
}

export function ProcessingView({
  summary,
  onRetry,
  retrying = false,
  retryError = null,
  since,
}: {
  summary: AnalysisSummary;
  onRetry: () => void;
  retrying?: boolean;
  retryError?: string | null;
  since: number;
}) {
  return (
    <div className="mx-auto max-w-xl rounded-2xl border border-border bg-surface p-6 sm:p-8">
      {summary.status === "failed" ? (
        <Failed summary={summary} onRetry={onRetry} retrying={retrying} retryError={retryError} />
      ) : summary.status === "awaiting_upload" ? (
        <div className="space-y-3">
          <h1 className="text-2xl font-semibold tracking-tight">This upload didn't finish</h1>
          <p className="text-ink-muted">The video never reached us, so there's nothing to analyze yet.</p>
          <Link to="/" className="inline-block rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent">
            Upload it again
          </Link>
        </div>
      ) : (
        <Stages summary={summary} since={since} />
      )}
    </div>
  );
}
