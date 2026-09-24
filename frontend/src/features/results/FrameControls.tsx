import { useId, useState, type ReactNode } from "react";

import { usePlayhead, usePlayheadStore } from "../../playhead/context";
import { SHORTCUT_HELP } from "./shortcuts";

export const SPEEDS = [0.25, 0.5, 1] as const;

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="grid size-9 place-items-center rounded-lg text-ink hover:bg-surface-2"
    >
      {children}
    </button>
  );
}

const icon = "size-5";

function PlayPauseButton() {
  const store = usePlayheadStore();
  const playing = usePlayhead((s) => s.playing);
  return (
    <button
      type="button"
      onClick={store.togglePlay}
      aria-label={playing ? "Pause" : "Play"}
      title={`${playing ? "Pause" : "Play"} (Space)`}
      className="grid size-11 place-items-center rounded-full bg-accent text-on-accent hover:bg-accent-strong"
      data-testid="play-pause"
    >
      {playing ? (
        <svg viewBox="0 0 24 24" className={icon} fill="currentColor" aria-hidden>
          <rect x="6" y="5" width="4" height="14" rx="1" />
          <rect x="14" y="5" width="4" height="14" rx="1" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className={icon} fill="currentColor" aria-hidden>
          <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.2-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" />
        </svg>
      )}
    </button>
  );
}

function SpeedSelector() {
  const store = usePlayheadStore();
  const rate = usePlayhead((s) => s.rate);
  return (
    <div role="radiogroup" aria-label="Playback speed" className="inline-flex rounded-lg border border-border bg-surface p-0.5 text-sm">
      {SPEEDS.map((speed) => (
        <button
          key={speed}
          type="button"
          role="radio"
          aria-checked={rate === speed}
          onClick={() => store.setRate(speed)}
          className={`tabular rounded-md px-2.5 py-1 font-medium ${
            rate === speed ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
          }`}
        >
          {speed}×
        </button>
      ))}
    </div>
  );
}

function ShortcutsHelp() {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="grid size-9 place-items-center rounded-lg border border-border text-sm font-semibold text-ink-muted hover:text-ink"
        title="Keyboard shortcuts"
      >
        <span aria-hidden>?</span>
        <span className="sr-only">Keyboard shortcuts</span>
      </button>
      {open && (
        <div
          id={id}
          className="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-border bg-surface p-3 shadow-xl"
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        >
          <h3 className="mb-2 text-sm font-semibold">Keyboard shortcuts</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
            {SHORTCUT_HELP.map(([keys, description]) => (
              <div key={keys} className="contents">
                <dt>
                  <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-xs">{keys}</kbd>
                </dt>
                <dd className="text-ink-muted">{description}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

export function FrameControls({ children }: { children?: ReactNode }) {
  const store = usePlayheadStore();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2" role="toolbar" aria-label="Playback controls">
      <div className="flex items-center gap-1">
        <IconButton label="Previous frame" onClick={() => store.step(-1)}>
          <svg viewBox="0 0 24 24" className={icon} fill="currentColor" aria-hidden>
            <rect x="5" y="5" width="2.5" height="14" rx="1" />
            <path d="M19 6.2v11.6a1 1 0 0 1-1.54.84L9.4 13.3a1.5 1.5 0 0 1 0-2.6l8.06-5.34A1 1 0 0 1 19 6.2Z" />
          </svg>
        </IconButton>
        <PlayPauseButton />
        <IconButton label="Next frame" onClick={() => store.step(1)}>
          <svg viewBox="0 0 24 24" className={icon} fill="currentColor" aria-hidden>
            <rect x="16.5" y="5" width="2.5" height="14" rx="1" />
            <path d="M5 6.2v11.6a1 1 0 0 0 1.54.84l8.06-5.34a1.5 1.5 0 0 0 0-2.6L6.54 5.36A1 1 0 0 0 5 6.2Z" />
          </svg>
        </IconButton>
      </div>
      <SpeedSelector />
      {children}
      <div className="ml-auto">
        <ShortcutsHelp />
      </div>
    </div>
  );
}
