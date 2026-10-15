import { Navigate, Outlet, useLocation } from "react-router";

import { useProfile } from "../../api/profile";
import { useSession } from "../../api/session";
import { nextParam } from "../../lib/safeNext";

/** Layout route: renders its pages only when signed in, otherwise sends the user to sign in. */
export const CHOOSE_USERNAME = "/choose-username";

export function RequireAuth() {
  const session = useSession();
  const location = useLocation();
  const profile = useProfile(Boolean(session.data));

  if (session.isPending) {
    return <p role="status" className="py-8 text-ink-muted">Loading…</p>;
  }
  if (session.isError) {
    return (
      <div role="alert" className="space-y-3 py-8">
        <p>We couldn't reach the server.</p>
        <button
          type="button"
          onClick={() => session.refetch()}
          className="rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent hover:bg-accent-strong"
        >
          Try again
        </button>
      </div>
    );
  }
  if (!session.data) {
    return <Navigate to={`/login${nextParam(location.pathname + location.search)}`} replace />;
  }
  // Every account has a username; one from before that was required chooses it first.
  if (profile.data && !profile.data.username && location.pathname !== CHOOSE_USERNAME) {
    return <Navigate to={`${CHOOSE_USERNAME}${nextParam(location.pathname + location.search)}`} replace />;
  }
  return <Outlet />;
}
