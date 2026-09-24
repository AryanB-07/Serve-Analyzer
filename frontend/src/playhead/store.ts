import { clampFrame } from "../lib/time";

export interface PlayheadState {
  frame: number;
  playing: boolean;
  rate: number;
}

export type PlayheadCommand =
  | { type: "seek"; frame: number }
  | { type: "play" }
  | { type: "pause" }
  | { type: "rate"; rate: number };

type Listener = () => void;
type CommandListener = (command: PlayheadCommand) => void;

/**
 * Single source of truth for "where are we in the clip".
 *
 * Two directions:
 *  - Commands (seek/play/pause/rate) come from UI controls and are forwarded
 *    to whoever owns the media element.
 *  - Reports (reportFrame/reportPlaying/reportRate) come from the media element
 *    and update state.
 *
 * `seek` also sets the frame immediately so paused UIs respond without
 * waiting for the video to decode the target frame.
 */
export interface PlayheadStore {
  readonly nFrames: number;
  readonly fps: number;
  getState(): PlayheadState;
  subscribe(listener: Listener): () => void;
  onCommand(listener: CommandListener): () => void;
  seek(frame: number): void;
  step(delta: number): void;
  play(): void;
  pause(): void;
  togglePlay(): void;
  setRate(rate: number): void;
  reportFrame(frame: number): void;
  reportPlaying(playing: boolean): void;
  reportRate(rate: number): void;
}

export function createPlayheadStore(nFrames: number, fps: number): PlayheadStore {
  let state: PlayheadState = { frame: 0, playing: false, rate: 1 };
  const listeners = new Set<Listener>();
  const commandListeners = new Set<CommandListener>();

  function set(patch: Partial<PlayheadState>) {
    const next = { ...state, ...patch };
    if (next.frame === state.frame && next.playing === state.playing && next.rate === state.rate) {
      return;
    }
    state = next;
    for (const l of listeners) l();
  }

  function command(c: PlayheadCommand) {
    for (const l of commandListeners) l(c);
  }

  const store: PlayheadStore = {
    nFrames,
    fps,
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    onCommand(listener) {
      commandListeners.add(listener);
      return () => commandListeners.delete(listener);
    },
    seek(frame) {
      const target = clampFrame(frame, nFrames);
      set({ frame: target });
      command({ type: "seek", frame: target });
    },
    step(delta) {
      if (state.playing) store.pause();
      store.seek(state.frame + delta);
    },
    play: () => command({ type: "play" }),
    pause: () => command({ type: "pause" }),
    togglePlay: () => (state.playing ? store.pause() : store.play()),
    setRate: (rate) => command({ type: "rate", rate }),
    reportFrame: (frame) => set({ frame: clampFrame(frame, nFrames) }),
    reportPlaying: (playing) => set({ playing }),
    reportRate: (rate) => set({ rate }),
  };
  return store;
}
