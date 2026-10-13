import { useEffect, useId, useRef, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

import type { HelpTopic } from "./topics";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * The help dialog: a tab per topic, and the selected topic's page. A modal: focus stays inside
 * (the page behind is made inert by HelpProvider, which also returns focus to whatever opened
 * it), and Escape or the backdrop closes it.
 */
export function HelpDialog({ topics, topic, onSelect, onClose }: {
  topics: HelpTopic[];
  topic: HelpTopic;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const id = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());

  // Focus the selected tab on open, and keep the page behind from scrolling.
  useEffect(() => {
    tabRefs.current.get(topic.id)?.focus();
    const root = document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = "hidden";
    return () => {
      root.style.overflow = overflow;
    };
    // Only on open and close; switching topics keeps focus where the user put it.
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !panelRef.current) return;
    const items = [...panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.closest("[hidden]"));
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  /** Arrow keys move between tabs (vertical on wide screens, a row on phones, so both work). */
  function onTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key];
    const target = event.key === "Home" ? 0 : event.key === "End" ? topics.length - 1
      : step !== undefined ? (index + step + topics.length) % topics.length : null;
    if (target === null) return;
    event.preventDefault();
    const next = topics[target]!;
    onSelect(next.id);
    tabRefs.current.get(next.id)?.focus();
  }

  const Body = topic.Body;
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center sm:p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        onKeyDown={onKeyDown}
        className="flex max-h-[92dvh] w-full max-w-3xl flex-col overflow-hidden rounded-t-2xl border border-border bg-bg shadow-2xl sm:max-h-[85dvh] sm:rounded-2xl"
      >
        <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
          <h2 id={`${id}-title`} className="text-lg font-semibold">Help</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close help"
            className="-mr-1 grid size-9 place-items-center rounded-lg text-ink-muted hover:bg-surface-2 hover:text-ink"
          >
            <svg viewBox="0 0 20 20" className="size-5" aria-hidden>
              <path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </header>
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <div
            role="tablist"
            aria-label="Help topics"
            aria-orientation="vertical"
            className="flex shrink-0 gap-1 overflow-x-auto border-b border-border p-2 md:w-56 md:flex-col md:overflow-x-visible md:border-r md:border-b-0"
          >
            {topics.map((t, index) => {
              const selected = t.id === topic.id;
              return (
                <button
                  key={t.id}
                  ref={(el) => {
                    if (el) tabRefs.current.set(t.id, el);
                    else tabRefs.current.delete(t.id);
                  }}
                  type="button"
                  role="tab"
                  id={`${id}-tab-${t.id}`}
                  aria-selected={selected}
                  aria-controls={`${id}-panel`}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => onSelect(t.id)}
                  onKeyDown={(e) => onTabKey(e, index)}
                  className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm font-medium whitespace-nowrap md:whitespace-normal ${
                    selected ? "bg-surface-2 text-ink" : "text-ink-muted hover:bg-surface hover:text-ink"
                  }`}
                >
                  {t.title}
                </button>
              );
            })}
          </div>
          <div
            role="tabpanel"
            id={`${id}-panel`}
            aria-labelledby={`${id}-tab-${topic.id}`}
            tabIndex={0}
            className="min-h-0 flex-1 overflow-y-auto p-5 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/60"
          >
            <h3 className="mb-4 text-xl font-semibold tracking-tight">{topic.title}</h3>
            <Body />
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
