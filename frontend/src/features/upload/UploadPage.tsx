import { Link } from "react-router";

import { USE_MOCKS } from "../../api";
import { DEMO_IDS } from "../../api/demo";

/** Milestone 2 placeholder. The upload flow arrives in milestone 7. */
export function UploadPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Analyze a serve</h1>
      <p className="text-ink-muted">Upload is coming in milestone 7.</p>
      {USE_MOCKS && (
        <Link
          to={`/analyses/${DEMO_IDS[0]}`}
          className="inline-block rounded-lg bg-accent px-4 py-2 font-medium text-on-accent hover:bg-accent-strong"
        >
          Open the demo analysis
        </Link>
      )}
    </div>
  );
}
