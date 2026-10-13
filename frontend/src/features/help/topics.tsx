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
  { id: "limits", title: "What the analysis can't do", Body: Limits },
  { id: "shortcuts", title: "Keyboard shortcuts", Body: Shortcuts },
];

export function findTopic(id: string | null | undefined, topics: HelpTopic[] = HELP_TOPICS): HelpTopic | undefined {
  return topics.find((t) => t.id === id);
}
