import { describe, expect, it, vi } from "vitest";

import { createPlayheadStore, type PlayheadCommand } from "./store";

function setup() {
  const store = createPlayheadStore(100, 25);
  const commands: PlayheadCommand[] = [];
  store.onCommand((c) => commands.push(c));
  const listener = vi.fn();
  store.subscribe(listener);
  return { store, commands, listener };
}

describe("playhead store", () => {
  it("seek updates the frame immediately and forwards a clamped command", () => {
    const { store, commands, listener } = setup();
    store.seek(250);
    expect(store.getState().frame).toBe(99);
    expect(commands).toEqual([{ type: "seek", frame: 99 }]);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("notifies only when state actually changes", () => {
    const { store, listener } = setup();
    store.reportFrame(5);
    store.reportFrame(5);
    store.reportPlaying(false);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("play/pause/rate are commands; state follows the media reports", () => {
    const { store, commands } = setup();
    store.togglePlay();
    expect(commands.at(-1)).toEqual({ type: "play" });
    expect(store.getState().playing).toBe(false);
    store.reportPlaying(true);
    store.togglePlay();
    expect(commands.at(-1)).toEqual({ type: "pause" });
    store.setRate(0.25);
    expect(commands.at(-1)).toEqual({ type: "rate", rate: 0.25 });
    store.reportRate(0.25);
    expect(store.getState().rate).toBe(0.25);
  });

  it("step pauses playback and moves one frame", () => {
    const { store, commands } = setup();
    store.reportFrame(10);
    store.reportPlaying(true);
    store.step(-1);
    expect(commands).toEqual([{ type: "pause" }, { type: "seek", frame: 9 }]);
    expect(store.getState().frame).toBe(9);
  });

  it("unsubscribes", () => {
    const store = createPlayheadStore(10, 25);
    const listener = vi.fn();
    const off = store.subscribe(listener);
    off();
    store.seek(3);
    expect(listener).not.toHaveBeenCalled();
  });
});
