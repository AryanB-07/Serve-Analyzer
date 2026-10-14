import { Link } from "react-router";

import { PUBLIC_DEMO_ID } from "../../api/demo";
import { useSession } from "../../api/session";
import { ResultsPage } from "../results/ResultsPage";

const SOURCE =
  "https://commons.wikimedia.org/wiki/File:Intention-understanding-over-T-a-neuroimaging-study-on-shared-representations-and-tennis-return-Movie1.ogv";

/** A real analysis anyone can open, no account needed: what the app does, in one page. */
export function DemoPage() {
  const signedIn = Boolean(useSession().data);
  const action = "rounded-lg px-4 py-2 text-sm font-semibold";
  return (
    <div className="space-y-6">
      <section aria-labelledby="demo-heading" className="space-y-3 rounded-xl border border-accent/40 bg-accent/5 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 id="demo-heading" className="text-xl font-semibold tracking-tight">Sample analysis</h1>
            <p className="max-w-2xl text-sm text-ink-muted">
              This is what you get for your own serve: your skeleton tracked on the video, the trophy position and contact
              marked on the timeline, joint angles frame by frame, and feedback. Play it, scrub it, or press 1 and 3 to
              jump between phases.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {signedIn ? (
              <Link to="/" className={`${action} bg-accent text-on-accent hover:bg-accent-strong`}>Analyze your serve</Link>
            ) : (
              <>
                <Link to="/signup" className={`${action} bg-accent text-on-accent hover:bg-accent-strong`}>Create a free account</Link>
                <Link to="/login" className={`${action} border border-border hover:bg-surface-2`}>Sign in</Link>
              </>
            )}
          </div>
        </div>
        <p className="text-xs text-ink-muted">
          Video: Cacioppo et al. (2014), <i>Frontiers in Human Neuroscience</i>,{" "}
          <a href={SOURCE} className="underline hover:text-ink" rel="noreferrer">Wikimedia Commons</a>, CC BY 4.0. It was
          filmed from across the net rather than side-on, so its angles aren't typical of a well-filmed serve.
        </p>
      </section>
      <ResultsPage demoId={PUBLIC_DEMO_ID} />
    </div>
  );
}
