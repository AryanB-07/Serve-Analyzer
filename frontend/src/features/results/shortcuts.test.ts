import { describe, expect, it } from "vitest";

import { createPlayheadStore, type PlayheadCommand } from "../../playhead/store";
import { applyShortcut, shortcutFor, shouldIgnore } from "./shortcuts";

const key = (k: string, mods: Partial<KeyboardEvent> = {}) => ({
  key: k, shiftKey: false, metaKey: false, ctrlKey: false, altKey: false, ...mods,
});

describe("shortcutFor", () => {
  it("maps the documented keys", () => {
    expect(shortcutFor(key(" "))).toEqual({ type: "toggle" });
    expect(shortcutFor(key("k"))).toEqual({ type: "toggle" });
    expect(shortcutFor(key("ArrowLeft"))).toEqual({ type: "step", frames: -1 });
    expect(shortcutFor(key("ArrowRight", { shiftKey: true }))).toEqual({ type: "step", frames: 10 });
    expect(shortcutFor(key("."))).toEqual({ type: "step", frames: 1 });
    expect(shortcutFor(key("J"))).toEqual({ type: "stepSeconds", seconds: -1 });
    expect(shortcutFor(key("l"))).toEqual({ type: "stepSeconds", seconds: 1 });
    expect(shortcutFor(key("3"))).toEqual({ type: "phase", phase: "contact" });
    expect(shortcutFor(key("End"))).toEqual({ type: "edge", to: "end" });
  });

  it("leaves browser shortcuts and unknown keys alone", () => {
    expect(shortcutFor(key("l", { metaKey: true }))).toBeNull();
    expect(shortcutFor(key("ArrowLeft", { altKey: true }))).toBeNull();
    expect(shortcutFor(key("x"))).toBeNull();
  });
});

describe("applyShortcut", () => {
  function setup() {
    const store = createPlayheadStore(125, 25);
    const commands: PlayheadCommand[] = [];
    store.onCommand((c) => commands.push(c));
    return { store, commands };
  }
  const phases = { trophy: 113, racket_drop: null, contact: 124 };

  it("steps by a second of frames", () => {
    const { store } = setup();
    store.reportFrame(50);
    applyShortcut({ type: "stepSeconds", seconds: -1 }, store, phases);
    expect(store.getState().frame).toBe(25);
  });

  it("jumps to a detected phase and refuses an undetected one", () => {
    const { store } = setup();
    expect(applyShortcut({ type: "phase", phase: "contact" }, store, phases)).toBe(true);
    expect(store.getState().frame).toBe(124);
    expect(applyShortcut({ type: "phase", phase: "racket_drop" }, store, phases)).toBe(false);
    expect(store.getState().frame).toBe(124);
  });

  it("jumps to the clip edges", () => {
    const { store, commands } = setup();
    applyShortcut({ type: "edge", to: "end" }, store, phases);
    expect(commands.at(-1)).toEqual({ type: "seek", frame: 124 });
  });
});

describe("shouldIgnore", () => {
  it("never steals typing", () => {
    expect(shouldIgnore(document.createElement("input"), "k")).toBe(true);
    expect(shouldIgnore(document.createElement("textarea"), " ")).toBe(true);
  });

  it("lets Space activate a focused button but still handles arrows there", () => {
    const button = document.createElement("button");
    expect(shouldIgnore(button, " ")).toBe(true);
    expect(shouldIgnore(button, "ArrowRight")).toBe(false);
    expect(shouldIgnore(document.body, " ")).toBe(false);
  });
});
