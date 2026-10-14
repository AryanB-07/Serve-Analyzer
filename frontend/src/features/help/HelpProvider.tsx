import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { HelpDialog } from "./HelpDialog";
import { findTopic, HELP_TOPICS, type HelpTopic } from "./topics";

/** The search parameter holding the open topic: /history?help=filming opens the filming guide. */
export const HELP_PARAM = "help";

interface HelpContextValue {
  /** Open the help dialog, at ``topicId`` (the first topic by default). */
  openHelp: (topicId?: string) => void;
  closeHelp: () => void;
  isOpen: boolean;
}

const HelpContext = createContext<HelpContextValue | null>(null);

/** Like useHelp, but null outside a HelpProvider: for parts that also render on their own. */
export function useOptionalHelp(): HelpContextValue | null {
  return useContext(HelpContext);
}

export function useHelp(): HelpContextValue {
  const value = useContext(HelpContext);
  if (!value) throw new Error("useHelp needs a <HelpProvider> (AppShell has one)");
  return value;
}

/**
 * Owns the help dialog. The open topic lives in the URL (?help=<id>), so a link can open help
 * at a topic, and the browser's back button closes it, as people expect on phones.
 */
export function HelpProvider({ children, topics = HELP_TOPICS }: { children: ReactNode; topics?: HelpTopic[] }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get(HELP_PARAM);
  // An unknown id (an old link) still opens help, at the first topic.
  const topic = requested === null ? null : (findTopic(requested, topics) ?? topics[0] ?? null);

  const setTopic = useCallback(
    (id: string | null, replace: boolean) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (id === null) next.delete(HELP_PARAM);
          else next.set(HELP_PARAM, id);
          return next;
        },
        { replace, preventScrollReset: true },
      ),
    [setParams],
  );

  // Where focus goes back to when the dialog closes (by any route: button, Escape, Back).
  const opener = useRef<HTMLElement | null>(null);
  const isOpen = topic !== null;
  useEffect(() => {
    if (!isOpen && opener.current) {
      opener.current.focus();
      opener.current = null;
    }
  }, [isOpen]);

  const value = useMemo<HelpContextValue>(
    () => ({
      openHelp: (topicId) => {
        if (!isOpen && document.activeElement instanceof HTMLElement) opener.current = document.activeElement;
        // Opening adds a history entry (so Back closes it); switching topics doesn't.
        setTopic(topicId ?? topics[0]!.id, isOpen);
      },
      closeHelp: () => setTopic(null, true),
      isOpen,
    }),
    [setTopic, isOpen, topics],
  );

  return (
    <HelpContext.Provider value={value}>
      {/* The page behind a modal can't be clicked, focused or read by screen readers. */}
      <div className="contents" inert={isOpen}>
        {children}
      </div>
      {topic && (
        <HelpDialog
          topics={topics}
          topic={topic}
          onSelect={(id) => setTopic(id, true)}
          onClose={value.closeHelp}
        />
      )}
    </HelpContext.Provider>
  );
}

/** The ? button in the header. */
export function HelpButton() {
  const { openHelp, isOpen } = useHelp();
  return (
    <button
      type="button"
      onClick={() => openHelp()}
      aria-label="Help"
      aria-haspopup="dialog"
      aria-expanded={isOpen}
      title="Help"
      className="grid size-9 place-items-center rounded-lg border border-border text-ink-muted hover:bg-surface-2 hover:text-ink"
    >
      <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
        <circle cx="12" cy="12" r="9.5" />
        <path d="M9.4 9.2a2.7 2.7 0 0 1 5.2 1c0 1.8-2.6 2.4-2.6 4" />
        <path d="M12 17.6v.1" strokeWidth="2.6" />
      </svg>
    </button>
  );
}
