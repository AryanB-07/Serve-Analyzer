import { Link, NavLink, Outlet, useNavigate } from "react-router";

import { USE_MOCKS } from "../api";
import { useLogOut, useSession } from "../api/session";
import { ThemeToggle } from "./ThemeToggle";

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-3 py-1.5 text-sm font-medium ${
    isActive ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
  }`;
}

function AccountControls() {
  const session = useSession();
  const logOut = useLogOut();
  const navigate = useNavigate();
  const user = session.data;
  if (!user) return null;
  return (
    <>
      <Link
        to="/account"
        className="max-w-48 truncate rounded-md px-2 py-1.5 text-sm text-ink-muted hover:text-ink"
        title={`Account: ${user.email}`}
      >
        <span className="hidden md:inline">{user.email}</span>
        <span className="md:hidden">Account</span>
      </Link>
      <button
        type="button"
        onClick={() => logOut.mutate(undefined, { onSettled: () => navigate("/login", { replace: true }) })}
        disabled={logOut.isPending}
        className="rounded-md px-3 py-1.5 text-sm font-medium text-ink-muted hover:text-ink disabled:opacity-50"
      >
        Sign out
      </button>
    </>
  );
}

export function AppShell() {
  const signedIn = Boolean(useSession().data);
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-on-accent"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
          <NavLink
            to="/"
            aria-label="Serve Analyzer home"
            className="flex shrink-0 items-center gap-2 font-semibold tracking-tight"
          >
            <svg viewBox="0 0 24 24" className="size-6 text-accent" aria-hidden>
              <circle cx="12" cy="12" r="10" fill="currentColor" />
              <path d="M4.5 6.5c3.5 2 3.5 9 0 11M19.5 6.5c-3.5 2-3.5 9 0 11" fill="none" stroke="var(--bg)" strokeWidth="1.6" />
            </svg>
            <span className="hidden sm:inline">Serve Analyzer</span>
          </NavLink>
          {signedIn && (
            <nav aria-label="Main" className="flex items-center gap-1">
              <NavLink to="/" end className={navClass}>
                Analyze
              </NavLink>
              <NavLink to="/history" className={navClass}>
                History
              </NavLink>
            </nav>
          )}
          <div className="ml-auto flex items-center gap-3">
            {USE_MOCKS && (
              <span className="whitespace-nowrap rounded-full border border-warn/40 px-2 py-0.5 text-xs font-medium text-warn">
                Mock data
              </span>
            )}
            <ThemeToggle />
            <AccountControls />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs text-ink-muted">
          <span>Serve Analyzer · Tennis serve biomechanics, frame by frame</span>
          <nav aria-label="Legal" className="flex gap-4">
            <Link to="/privacy" className="hover:text-ink">Privacy</Link>
            <Link to="/terms" className="hover:text-ink">Terms</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
