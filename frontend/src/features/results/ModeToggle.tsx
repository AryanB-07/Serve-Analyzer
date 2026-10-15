import type { ResultsMode } from "../../lib/useResultsMode";
import { useOptionalHelp } from "../help/HelpProvider";

const OPTIONS: { value: ResultsMode; label: string; hint: string }[] = [
  { value: "simple", label: "Simple", hint: "Scores out of 100 and plain feedback" },
  { value: "advanced", label: "Advanced", hint: "Exact angles, confidence and error ranges" },
];

/** Simple or advanced results: a segmented control of native radios. */
export function ModeToggle({ mode, onChange }: { mode: ResultsMode; onChange: (mode: ResultsMode) => void }) {
  const help = useOptionalHelp();
  return (
    <fieldset className="flex flex-wrap items-center gap-2">
      <legend className="sr-only">How to show the results</legend>
      <div className="inline-flex rounded-lg border border-border bg-surface p-0.5">
        {OPTIONS.map((o) => (
          <label
            key={o.value}
            title={o.hint}
            className={`cursor-pointer rounded-md px-3 py-1.5 text-sm font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
              mode === o.value ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
            }`}
          >
            <input
              type="radio"
              name="results-mode"
              value={o.value}
              checked={mode === o.value}
              onChange={() => onChange(o.value)}
              className="sr-only"
              aria-description={o.hint}
            />
            {o.label}
          </label>
        ))}
      </div>
      {help && (
        <button type="button" onClick={() => help.openHelp("results")} className="text-sm text-accent hover:underline">
          What do these mean?
        </button>
      )}
    </fieldset>
  );
}
