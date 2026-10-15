import type { ComponentType } from "react";

import { LimitsList } from "../../components/KnownLimits";
import { SHORTCUT_HELP } from "../results/shortcuts";
import { FilmingTips } from "../upload/FilmingGuide";
import { GettingStartedSteps } from "../upload/Welcome";

/**
 * One page of the help dialog. To add help for a new feature, write its Body and add an entry
 * to HELP_TOPICS; the dialog lists the topics in that order.
 */
export interface HelpTopic {
  /** Stable and URL-safe: links open a topic with ?help=<id>, and code with openHelp(id). */
  id: string;
  title: string;
  Body: ComponentType;
}

function GettingStarted() {
  return (
    <div className="space-y-4">
      <GettingStartedSteps />
      <p className="text-sm text-ink-muted">
        Every analysis is kept in <strong className="text-ink">History</strong>, where you can open, compare or delete
        it.
      </p>
    </div>
  );
}

function Filming() {
  return (
    <div className="space-y-4">
      <FilmingTips />
    </div>
  );
}

function Limits() {
  return (
    <div className="space-y-4">
      <LimitsList />
      <p className="text-sm text-ink-muted">
        Spotted a mistake? Use <strong className="text-ink">This result looks wrong?</strong> under a result, so we can
        fix it.
      </p>
    </div>
  );
}

function ReadingResults() {
  const item = "text-sm";
  return (
    <div className="space-y-4 text-sm">
      <section className="space-y-1.5">
        <h4 className="font-semibold">Simple mode</h4>
        <p className="text-ink-muted">
          Each key position gets a score out of 100 for how close it is to the reference range: 80–100 is good, 50–79
          is borderline, below 50 needs work. The serve score is their average. Feedback is in plain words.
        </p>
        <p className="text-ink-muted">
          The ranges are general guides from coaching literature, not tailored to you, so read a score as "how far from
          typical", not as a grade.
        </p>
      </section>
      <section className="space-y-1.5">
        <h4 className="font-semibold">Advanced mode</h4>
        <ul className="list-disc space-y-1 pl-5 text-ink-muted">
          <li className={item}>
            <strong className="text-ink">The exact angle</strong>, to a tenth of a degree, against its good range.
          </li>
          <li className={item}>
            <strong className="text-ink">Tracking confidence:</strong> how sure the pose model was of the joints that
            measurement uses, taking the least certain one. High is 80% or more; below 50% the angle may be guessed.
          </li>
          <li className={item}>
            <strong className="text-ink">Tracking noise:</strong> how much the angle wobbles from frame to frame around
            that moment.
          </li>
          <li className={item}>
            <strong className="text-ink">Camera angle error:</strong> how far a single camera can be off for that
            measurement from where it was (9 times out of 10, on test footage). If you didn't say where the camera was,
            it assumes side-on from your hitting-arm side.
          </li>
          <li className={item}>
            <strong className="text-ink">Likely range:</strong> the angle plus or minus both errors, shown as the shaded
            band on the slider. The true angle is most likely inside it.
          </li>
        </ul>
      </section>
    </div>
  );
}

function Shortcuts() {
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-muted">On a results page, unless you are typing in a box:</p>
      <table className="w-full text-sm">
        <thead className="sr-only">
          <tr>
            <th scope="col">Keys</th>
            <th scope="col">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {SHORTCUT_HELP.map(([keys, action]) => (
            <tr key={keys}>
              <td className="py-1.5 pr-4 font-mono text-xs whitespace-nowrap">{keys}</td>
              <td className="py-1.5 text-ink-muted">{action}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const HELP_TOPICS: HelpTopic[] = [
  { id: "getting-started", title: "Getting started", Body: GettingStarted },
  { id: "filming", title: "How to film your serve", Body: Filming },
  { id: "results", title: "Reading your results", Body: ReadingResults },
  { id: "limits", title: "What the analysis can't do", Body: Limits },
  { id: "shortcuts", title: "Keyboard shortcuts", Body: Shortcuts },
];

export function findTopic(id: string | null | undefined, topics: HelpTopic[] = HELP_TOPICS): HelpTopic | undefined {
  return topics.find((t) => t.id === id);
}
