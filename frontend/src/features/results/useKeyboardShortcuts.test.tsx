import { fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePlayheadStore } from "../../playhead/context";
import { renderWithPlayhead } from "../../test/playhead";
import { useKeyboardShortcuts } from "./useKeyboardShortcuts";

const phases = { trophy: 113, racket_drop: null, contact: 124 };

function Shortcuts() {
  useKeyboardShortcuts(usePlayheadStore(), phases);
  return <input aria-label="notes" />;
}

describe("useKeyboardShortcuts", () => {
  it("drives the playhead from the keyboard", () => {
    const view = renderWithPlayhead(<Shortcuts />);
    fireEvent.keyDown(window, { key: "3" });
    expect(view.store.getState().frame).toBe(124);
    fireEvent.keyDown(window, { key: "ArrowLeft", shiftKey: true });
    expect(view.store.getState().frame).toBe(114);
    fireEvent.keyDown(window, { key: " " });
    expect(view.commands.at(-1)).toEqual({ type: "play" });
  });

  it("ignores keys typed into a field", () => {
    const view = renderWithPlayhead(<Shortcuts />);
    fireEvent.keyDown(view.getByLabelText("notes"), { key: "3" });
    expect(view.store.getState().frame).toBe(0);
  });
});
