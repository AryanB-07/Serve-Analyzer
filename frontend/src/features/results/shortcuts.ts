import type { PhaseFrames, PhaseName } from "../../api/types";
import type { PlayheadStore } from "../../playhead/store";

export type ShortcutAction =
  | { type: "toggle" }
  | { type: "step"; frames: number }
  | { type: "stepSeconds"; seconds: number }
  | { type: "phase"; phase: PhaseName }
  | { type: "edge"; to: "start" | "end" };

export const SHORTCUT_HELP: [keys: string, description: string][] = [
  ["Space / K", "Play or pause"],
  ["← / →", "Previous / next frame"],
  ["Shift + ← / →", "Back / forward 10 frames"],
  ["J / L", "Back / forward 1 second"],
  ["1 / 2 / 3", "Jump to trophy / racket drop / contact"],
  ["Home / End", "First / last frame"],
];

const PHASE_KEYS: Record<string, PhaseName> = { "1": "trophy", "2": "racket_drop", "3": "contact" };

/** Map a key press to an action. Pure, so the mapping is unit-testable. */
export function shortcutFor(e: Pick<KeyboardEvent, "key" | "shiftKey" | "metaKey" | "ctrlKey" | "altKey">): ShortcutAction | null {
  if (e.metaKey || e.ctrlKey || e.altKey) return null;
  const big = e.shiftKey ? 10 : 1;
  switch (e.key) {
    case " ":
    case "k":
    case "K":
      return { type: "toggle" };
    case "ArrowLeft":
      return { type: "step", frames: -big };
    case "ArrowRight":
      return { type: "step", frames: big };
    case ",":
      return { type: "step", frames: -1 };
    case ".":
      return { type: "step", frames: 1 };
    case "j":
    case "J":
      return { type: "stepSeconds", seconds: -1 };
    case "l":
    case "L":
      return { type: "stepSeconds", seconds: 1 };
    case "Home":
      return { type: "edge", to: "start" };
    case "End":
      return { type: "edge", to: "end" };
  }
  const phase = PHASE_KEYS[e.key];
  return phase ? { type: "phase", phase } : null;
}

/** Returns false if the action could not apply (e.g. that phase wasn't detected). */
export function applyShortcut(action: ShortcutAction, store: PlayheadStore, phases: PhaseFrames): boolean {
  switch (action.type) {
    case "toggle":
      store.togglePlay();
      return true;
    case "step":
      store.step(action.frames);
      return true;
    case "stepSeconds":
      store.step(Math.round(action.seconds * store.fps));
      return true;
    case "edge":
      store.seek(action.to === "start" ? 0 : store.nFrames - 1);
      return true;
    case "phase": {
      const frame = phases[action.phase];
      if (frame === null) return false;
      store.seek(frame);
      return true;
    }
  }
}

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);
const ACTIVATES_ON_SPACE = new Set(["BUTTON", "A", "SUMMARY"]);

/**
 * Whether the page-level handler should ignore this key: never steal typing,
 * and let Space activate a focused button (otherwise pressing Space on a
 * focused control would toggle playback *and* click the control).
 */
export function shouldIgnore(target: EventTarget | null, key: string): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (TYPING.has(target.tagName) || target.isContentEditable) return true;
  if (key === " " && (ACTIVATES_ON_SPACE.has(target.tagName) || target.getAttribute("role") === "switch")) {
    return true;
  }
  return false;
}
