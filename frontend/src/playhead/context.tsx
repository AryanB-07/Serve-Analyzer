import { createContext, useContext, useState, useSyncExternalStore, type ReactNode } from "react";

import { createPlayheadStore, type PlayheadState, type PlayheadStore } from "./store";

const PlayheadContext = createContext<PlayheadStore | null>(null);

export function PlayheadProvider({
  nFrames,
  fps,
  children,
}: {
  nFrames: number;
  fps: number;
  children: ReactNode;
}) {
  const [store] = useState(() => createPlayheadStore(nFrames, fps));
  return <PlayheadContext.Provider value={store}>{children}</PlayheadContext.Provider>;
}

export function usePlayheadStore(): PlayheadStore {
  const store = useContext(PlayheadContext);
  if (!store) throw new Error("usePlayheadStore must be used inside <PlayheadProvider>");
  return store;
}

/**
 * Subscribe to a slice of playhead state. The component re-renders only when
 * the selected value changes, so e.g. a phase label re-renders ~4 times per
 * clip, not on every frame. Selectors must return primitives (or stable
 * references), as with any useSyncExternalStore snapshot.
 */
export function usePlayhead<T>(selector: (state: PlayheadState) => T): T {
  const store = usePlayheadStore();
  return useSyncExternalStore(store.subscribe, () => selector(store.getState()));
}
