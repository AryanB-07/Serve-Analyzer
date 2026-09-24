import type { OverlayOptions } from "./VideoStage";

function Switch({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2 rounded-md px-1 py-1 text-sm text-ink-muted hover:text-ink"
    >
      <span
        className={`relative inline-block h-5 w-9 shrink-0 rounded-full transition-colors ${checked ? "bg-accent" : "bg-surface-2 ring-1 ring-border"}`}
      >
        <span
          className={`absolute left-0 top-0.5 size-4 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-4.5" : "translate-x-0.5"}`}
        />
      </span>
      {label}
    </button>
  );
}

export function OverlayToggles({
  options,
  onChange,
}: {
  options: OverlayOptions;
  onChange: (options: OverlayOptions) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2" role="group" aria-label="Overlay options">
      <Switch
        label="Skeleton"
        checked={options.showSkeleton}
        onChange={(showSkeleton) => onChange({ ...options, showSkeleton })}
      />
      <Switch
        label="Angle labels"
        checked={options.showLabels}
        onChange={(showLabels) => onChange({ ...options, showLabels })}
      />
      <div
        role="radiogroup"
        aria-label="Landmark data"
        className="inline-flex rounded-lg border border-border bg-surface p-0.5 text-sm"
      >
        {(["smoothed", "raw"] as const).map((source) => (
          <button
            key={source}
            type="button"
            role="radio"
            aria-checked={options.source === source}
            onClick={() => onChange({ ...options, source })}
            className={`rounded-md px-3 py-1 font-medium capitalize ${
              options.source === source ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
            }`}
          >
            {source}
          </button>
        ))}
      </div>
    </div>
  );
}
