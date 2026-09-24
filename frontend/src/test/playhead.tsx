import { render } from "@testing-library/react";
import type { ReactNode } from "react";

import { PlayheadProvider, usePlayheadStore } from "../playhead/context";
import type { PlayheadCommand, PlayheadStore } from "../playhead/store";

/** Render inside a PlayheadProvider and expose the store plus the commands it sent. */
export function renderWithPlayhead(ui: ReactNode, { nFrames = 125, fps = 25 } = {}) {
  const handle: { store: PlayheadStore | null; commands: PlayheadCommand[] } = { store: null, commands: [] };
  function Capture() {
    const store = usePlayheadStore();
    if (handle.store !== store) {
      handle.store = store;
      store.onCommand((c) => handle.commands.push(c));
    }
    return null;
  }
  const utils = render(
    <PlayheadProvider nFrames={nFrames} fps={fps}>
      <Capture />
      {ui}
    </PlayheadProvider>,
  );
  return { ...utils, get store() { return handle.store!; }, commands: handle.commands };
}
