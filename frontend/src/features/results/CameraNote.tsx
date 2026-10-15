import type { AnalysisResult } from "../../api/types";
import { useOptionalHelp } from "../help/HelpProvider";
import { CAMERA_VIEWS, joinList, measurementName, measurementsWith } from "../../lib/quality";
import type { ResultsMode } from "../../lib/useResultsMode";

/**
 * What the camera position the person chose can and can't read. Shown above the measurements
 * when they answered "Where was your camera?"; without an answer there's a one-line tip instead.
 */
export function CameraNote({ result, mode = "advanced" }: { result: AnalysisResult; mode?: ResultsMode }) {
  const help = useOptionalHelp();
  const view = result.camera_view;
  if (!view || !result.quality) {
    return (
      <p className="text-xs text-ink-muted" data-testid="camera-tip">
        Every measurement is shown as measured. Next time, say where your camera was when you upload, and we'll mark
        the ones that position can't read.
      </p>
    );
  }
  const name = (m: { phase: Parameters<typeof measurementName>[0]; metric: Parameters<typeof measurementName>[1] }) =>
    measurementName(m.phase, m.metric);
  const unreadable = measurementsWith(result, "unreadable").map(name);
  const approximate = measurementsWith(result, "approximate").map(name);
  const one = unreadable.length === 1;
  return (
    <section aria-labelledby="camera-note-heading" className="space-y-2 rounded-xl border border-border bg-surface p-4">
      <h2 id="camera-note-heading" className="text-sm font-semibold">
        Filmed {CAMERA_VIEWS[view].long}
      </h2>
      {unreadable.length > 0 && (
        <p className="text-sm">
          From here, the {joinList(unreadable)} can't be read from one camera, so {one ? "it isn't" : "they aren't"} scored
          and {one ? "has" : "have"} no feedback.
        </p>
      )}
      {/* Simple mode's cards already say "rough from this angle", so it doesn't list them again. */}
      {approximate.length > 0 && mode === "advanced" && (
        <p className="text-sm text-ink-muted">
          The {joinList(approximate)} {approximate.length === 1 ? "is" : "are"} approximate from this angle.
        </p>
      )}
      {unreadable.length === 0 && approximate.length === 0 && (
        <p className="text-sm text-ink-muted">Every measurement reads well from this position.</p>
      )}
      {view !== "side_hitting" && unreadable.length > 0 && help && (
        <button type="button" onClick={() => help.openHelp("filming")} className="text-sm font-medium text-accent hover:underline">
          Where to put the camera
        </button>
      )}
    </section>
  );
}
