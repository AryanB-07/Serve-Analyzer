import type { Hand } from "../../api/types";

const OPTIONS: { value: Hand; label: string }[] = [
  { value: "right", label: "Right-handed" },
  { value: "left", label: "Left-handed" },
];

/** Native radios (keyboard and screen-reader behaviour for free), styled as a segmented control. */
export function HandSelector({
  value,
  onChange,
  disabled,
}: {
  value: Hand | null;
  onChange: (hand: Hand) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset disabled={disabled} className="space-y-2">
      <legend className="text-sm font-medium">Which hand do you serve with?</legend>
      <div className="grid grid-cols-2 gap-2">
        {OPTIONS.map((o) => (
          <label
            key={o.value}
            className={`flex cursor-pointer items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
              value === o.value ? "border-accent bg-accent/10 text-ink" : "border-border bg-surface text-ink-muted hover:text-ink"
            }`}
          >
            <input
              type="radio"
              name="hand"
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              className="sr-only"
            />
            {o.label}
          </label>
        ))}
      </div>
      <p className="text-xs text-ink-muted">This decides which arm is analysed as the hitting arm.</p>
    </fieldset>
  );
}
