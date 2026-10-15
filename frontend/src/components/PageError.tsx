import { useEffect } from "react";
import { Link, useRouteError } from "react-router";

/**
 * What a page shows if it crashes while rendering, in place of React Router's developer screen.
 * Inside the app shell, so the header and navigation still work.
 */
export function PageError() {
  const error = useRouteError();
  useEffect(() => {
    console.error("page crashed", error);
  }, [error]);
  return (
    <div role="alert" className="mx-auto max-w-lg space-y-3 py-10 text-center">
      <h1 className="text-2xl font-semibold">Something went wrong showing this page</h1>
      <p className="text-ink-muted">Your serves and results are safe. Reloading usually fixes it.</p>
      <div className="flex justify-center gap-3">
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent hover:bg-accent-strong"
        >
          Reload
        </button>
        <Link to="/" className="rounded-lg border border-border px-4 py-2 font-medium hover:bg-surface-2" reloadDocument>
          Back to upload
        </Link>
      </div>
    </div>
  );
}
