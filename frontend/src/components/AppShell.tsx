import { NavLink, Outlet } from "react-router";

import { USE_MOCKS } from "../api";
import { ThemeToggle } from "./ThemeToggle";

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-3 py-1.5 text-sm font-medium ${
    isActive ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
  }`;
}

export function AppShell() {
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
          <nav aria-label="Main" className="flex items-center gap-1">
            <NavLink to="/" end className={navClass}>
              Analyze
            </NavLink>
            <NavLink to="/history" className={navClass}>
              History
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {USE_MOCKS && (
              <span className="whitespace-nowrap rounded-full border border-warn/40 px-2 py-0.5 text-xs font-medium text-warn">
                Mock data
              </span>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
