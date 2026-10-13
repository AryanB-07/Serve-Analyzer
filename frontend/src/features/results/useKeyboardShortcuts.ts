import { useEffect } from "react";

import type { PhaseFrames } from "../../api/types";
import type { PlayheadStore } from "../../playhead/store";
import { applyShortcut, shortcutFor, shouldIgnore } from "./shortcuts";

/** Page-level playback shortcuts; see SHORTCUT_HELP for the list. */
export function useKeyboardShortcuts(store: PlayheadStore, phases: PhaseFrames): void {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.defaultPrevented || shouldIgnore(e.target, e.key)) return;
      // A dialog (such as Help) is open over the page: its keys aren't for the video.
      if (document.querySelector('[aria-modal="true"]')) return;
      const action = shortcutFor(e);
      if (!action) return;
      e.preventDefault();
      applyShortcut(action, store, phases);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [store, phases]);
}
