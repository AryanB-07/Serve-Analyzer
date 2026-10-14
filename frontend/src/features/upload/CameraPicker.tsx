import { useId } from "react";

import type { Hand } from "../../api/types";
import { CAMERA_VIEWS, type CameraView } from "../../lib/quality";

/**
 * Where was the camera? Eight positions around the player on a top-down court, plus "not sure".
 * Optional: the answer lets the results mark what that position can't read (guessing it from the
 * skeleton wasn't reliable enough; docs/view-detection.md). The court is drawn with the net at the
 * top, so for a right-hander the hitting-arm sideline is on the right; it mirrors for left-handers.
 */

type Cell = CameraView | "court";

const GRID_RIGHT_HANDED: Cell[] = [
  "front_diagonal_toss", "front", "front_diagonal_hitting",
  "side_toss", "court", "side_hitting",
  "behind_diagonal_toss", "behind", "behind_diagonal_hitting",
];

function mirrored(cells: Cell[]): Cell[] {
  return [0, 3, 6].flatMap((row) => cells.slice(row, row + 3).reverse());
}

function sideNote(view: CameraView): string | null {
  if (view.endsWith("_hitting")) return "hitting-arm side";
  if (view.endsWith("_toss")) return "other side";
  return null;
}

function Court({ hand }: { hand: Hand | null }) {
  const x = hand === "left" ? 18 : 42; // the player stands on their own side of the centre mark
  return (
    <svg viewBox="0 0 60 60" className="h-full w-full text-ink-muted" aria-hidden>
      <rect x="6" y="4" width="48" height="52" rx="2" fill="none" stroke="currentColor" strokeWidth="1" />
      <line x1="2" y1="14" x2="58" y2="14" stroke="currentColor" strokeWidth="2" strokeDasharray="2 2" />
      <text x="30" y="10" textAnchor="middle" fontSize="6" fill="currentColor">net</text>
      <circle cx={x} cy="46" r="4" className="fill-accent" />
      <path d={`M${x} 40 L${x} 26 M${x - 3} 30 L${x} 26 L${x + 3} 30`} fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

export function CameraPicker({ value, onChange, hand, disabled }: {
  value: CameraView | null;
  onChange: (view: CameraView | null) => void;
  hand: Hand | null;
  disabled?: boolean;
}) {
  const id = useId();
  const cells = hand === "left" ? mirrored(GRID_RIGHT_HANDED) : GRID_RIGHT_HANDED;
  const chip = (selected: boolean) =>
    `flex h-full cursor-pointer flex-col items-center justify-center gap-0.5 rounded-lg border px-1.5 py-2 text-center text-xs font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
      selected ? "border-accent bg-accent/10 text-ink" : "border-border bg-surface text-ink-muted hover:text-ink"
    }`;
  return (
    <fieldset disabled={disabled} className="space-y-2" aria-describedby={`${id}-hint`}>
      <legend className="text-sm font-medium">
        Where was your camera? <span className="font-normal text-ink-muted">(optional)</span>
      </legend>
      <p id={`${id}-hint`} className="text-xs text-ink-muted">
        Seen from above, with you serving up the court. It lets us mark the measurements that camera position can't
        read.{hand === null && " Choose your hand first to put your hitting-arm side in the right place."}
      </p>
      <div className="grid max-w-md grid-cols-3 gap-1.5">
        {cells.map((cell) =>
          cell === "court" ? (
            <div key="court" className="p-1">
              <Court hand={hand} />
            </div>
          ) : (
            <label key={cell} className={chip(value === cell)}>
              <input
                type="radio"
                name={`${id}-camera`}
                value={cell}
                checked={value === cell}
                onChange={() => onChange(cell)}
                aria-label={CAMERA_VIEWS[cell].long[0]!.toUpperCase() + CAMERA_VIEWS[cell].long.slice(1)}
                className="sr-only"
              />
              <span aria-hidden>{CAMERA_VIEWS[cell].short}</span>
              {sideNote(cell) && <span className="text-[11px] font-normal" aria-hidden>{sideNote(cell)}</span>}
              {cell === "side_hitting" && (
                <span className="mt-0.5 rounded-full border border-good/60 px-1.5 text-[10px] font-semibold text-good" aria-hidden>
                  filming guide
                </span>
              )}
            </label>
          ),
        )}
      </div>
      <label className={`${chip(value === null)} max-w-md flex-row py-1.5`}>
        <input
          type="radio"
          name={`${id}-camera`}
          value=""
          checked={value === null}
          onChange={() => onChange(null)}
          className="sr-only"
        />
        Not sure, or skip
      </label>
    </fieldset>
  );
}
