import { useState } from "react";

import { useAnalysesList } from "../../api/queries";

export const DISMISSED_KEY = "serve-analyzer:welcome-dismissed";

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false; // storage blocked: the card shows again next time, which is harmless
  }
}

function saveDismissed(): void {
  try {
    window.localStorage.setItem(DISMISSED_KEY, "1");
  } catch {
    // Not saved; it's dismissed for this visit anyway.
  }
}

/** Scroll to the filming guide and move focus there, so keyboard and screen-reader users land on it too. */
export function showFilmingGuide(): void {
  const guide = document.getElementById("filming-guide");
  if (!guide) return;
  guide.scrollIntoView({ behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  guide.focus({ preventScroll: true });
}

export const STEPS: [title: string, detail: string][] = [
  ["Film one serve, side-on", "The camera position matters more than anything else. The guide shows where to put your phone."],
  ["Choose your hand and upload", "Pick the hand you serve with, then drop in the clip. It takes about a minute to analyze."],
  ["Step through it frame by frame", "You'll see your skeleton on the video, your angles at the trophy position, racket drop and contact, and what to work on."],
];

/** The three numbered steps: in the welcome card, and in the help dialog's "Getting started". */
export function GettingStartedSteps() {
  return (
    <ol className="space-y-3">
      {STEPS.map(([title, detail], i) => (
        <li key={title} className="grid grid-cols-[auto_1fr] gap-x-3">
          <span className="tabular grid size-6 place-items-center rounded-full bg-accent text-xs font-semibold text-on-accent" aria-hidden>
            {i + 1}
          </span>
          <div>
            <p className="text-sm font-medium">{title}</p>
            <p className="text-sm text-ink-muted">{detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

/**
 * A first-visit walkthrough: shown until dismissed, and only while the account has no analyses
 * (someone with history already knows the way round). Its steps and the filming guide stay in
 * the help dialog (the ? button in the header) after it's gone.
 */
export function Welcome() {
  const history = useAnalysesList();
  const [dismissed, setDismissed] = useState(readDismissed);
  const firstPage = history.data?.pages[0];
  if (dismissed || !firstPage || firstPage.items.length > 0) return null;

  function dismiss() {
    saveDismissed();
    setDismissed(true);
  }

  return (
    <section aria-labelledby="welcome-heading" className="space-y-4 rounded-xl border border-accent/40 bg-accent/5 p-5">
      <div className="flex items-start justify-between gap-3">
        <h2 id="welcome-heading" className="text-lg font-semibold">Welcome! Your first analysis in three steps</h2>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss the welcome guide"
          className="-m-1 rounded-md p-1 text-ink-muted hover:text-ink"
        >
          <svg viewBox="0 0 20 20" className="size-5" aria-hidden>
            <path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <GettingStartedSteps />
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={showFilmingGuide}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong"
        >
          Show me how to film it
        </button>
        <button type="button" onClick={dismiss} className="text-sm font-medium text-ink-muted hover:text-ink">
          Got it
        </button>
      </div>
      <p className="text-xs text-ink-muted">
        This guide stays in Help: the{" "}
        <span className="inline-grid size-4 place-items-center rounded-full border border-border align-middle text-[10px] font-semibold" aria-hidden>
          ?
        </span>
        <span className="sr-only">question mark</span> button at the top of every page.
      </p>
    </section>
  );
}
