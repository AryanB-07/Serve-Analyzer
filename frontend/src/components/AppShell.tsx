import { useEffect, useId, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { USE_MOCKS } from "../api";
import { useUnreadCount } from "../api/messages";
import { useProfile } from "../api/profile";
import { useLogOut, useSession } from "../api/session";
import { SIGNING_OUT } from "../features/auth/AuthPages";
import { HelpButton, HelpProvider } from "../features/help/HelpProvider";
import { Avatar } from "./Avatar";
import { NotificationBell } from "./NotificationBell";
import { useMediaQuery } from "../lib/useMediaQuery";
import { ThemeToggle } from "./ThemeToggle";

function navClass({ isActive }: { isActive: boolean }) {
  return `whitespace-nowrap rounded-md px-2 py-1.5 text-sm font-medium sm:px-3 ${
    isActive ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"
  }`;
}

/**
 * Your picture, opening a small panel with Profile, Settings and Sign out. A disclosure (a
 * button that shows a list of links), so it works like any other link list for keyboards and
 * screen readers. Closes on Escape, a click outside, or choosing something.
 */
function AccountMenu() {
  const session = useSession();
  const profile = useProfile(Boolean(session.data));
  const navigate = useNavigate();
  const location = useLocation();
  const logOut = useLogOut(() => navigate("/login", { replace: true, flushSync: true, state: SIGNING_OUT }));
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    }
    function onPointer(event: PointerEvent) {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  const user = session.data;
  if (!user) return null;
  const p = profile.data;
  const name = p?.display_name ?? (p?.username ? `@${p.username}` : null);
  const item = "block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-surface-2";
  return (
    <div className="relative">
      <button
        ref={button}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={id}
        aria-label="Your account"
        title={user.email}
        className="flex items-center rounded-full p-0.5 ring-accent/50 hover:ring-2 focus-visible:ring-2"
      >
        <Avatar url={p?.avatar_url} name={p?.display_name ?? p?.username} size="sm" />
      </button>
      {open && (
        <div
          ref={panel}
          id={id}
          className="absolute right-0 top-full z-50 mt-2 w-60 rounded-xl border border-border bg-surface p-1.5 shadow-xl"
        >
          <div className="border-b border-border px-3 pb-2 pt-1.5">
            <p className="truncate text-sm font-medium">{name ?? "Your account"}</p>
            <p className="truncate text-xs text-ink-muted">{user.email}</p>
          </div>
          <ul className="pt-1.5">
            <li><Link to="/profile" className={item}>Profile</Link></li>
            <li><Link to="/settings" className={item}>Settings</Link></li>
            <li>
              <button type="button" onClick={() => logOut.mutate()} disabled={logOut.isPending} className={`${item} disabled:opacity-50`}>
                Sign out
              </button>
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}

const ICONS = {
  analyze: "M12 4v12M6 10l6-6 6 6M5 20h14",
  serves: "M4 6h16M4 12h16M4 18h10",
  friends: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM2 21c.8-3.6 3.6-6 7-6s6.2 2.4 7 6M16 3.5a4 4 0 0 1 0 7.5M18.5 15c1.9.9 3 2.9 3.5 6",
  messages: "M4 5h16v11H8l-4 4V5Z",
};

/** The main sections: in the header on wide screens, a tab bar along the bottom on phones. */
function MainNav({ phone }: { phone: boolean }) {
  const unread = useUnreadCount().data ?? 0;
  const items = [
    { to: "/", label: "Analyze", end: true, icon: ICONS.analyze, badge: 0, unit: "" },
    { to: "/serves", label: "My Serves", end: false, icon: ICONS.serves, badge: 0, unit: "" },
    { to: "/friends", label: "Friends", end: false, icon: ICONS.friends, badge: 0, unit: "" },
    { to: "/messages", label: "Messages", end: false, icon: ICONS.messages, badge: unread, unit: "message" },
  ];
  const badge = (n: number) =>
    n > 0 && (
      <span aria-hidden className="ml-1 inline-grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-4 text-on-accent">
        {n > 9 ? "9+" : n}
      </span>
    );
  // An explicit name, since browsers join a link's text pieces differently ("Friends , 1 new…").
  const label = (item: (typeof items)[number]) =>
    item.badge > 0 ? `${item.label}, ${item.badge} new ${item.unit}${item.badge === 1 ? "" : "s"}` : undefined;
  if (!phone) {
    return (
      <nav aria-label="Main" className="flex items-center gap-1">
        {items.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={navClass} aria-label={label(item)}>
            {item.label}
            {badge(item.badge)}
          </NavLink>
        ))}
      </nav>
    );
  }
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-bg/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
    >
      <ul className="mx-auto grid max-w-md grid-cols-4">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              aria-label={label(item)}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 py-2 text-xs font-medium ${isActive ? "text-accent" : "text-ink-muted hover:text-ink"}`}
            >
              <span className="relative">
                <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d={item.icon} />
                </svg>
                {item.badge > 0 && (
                  <span aria-hidden className="absolute -right-2 -top-1 grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-4 text-on-accent">
                    {item.badge > 9 ? "9+" : item.badge}
                  </span>
                )}
              </span>
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function AppShell() {
  return (
    <HelpProvider>
      <Shell />
    </HelpProvider>
  );
}

function Shell() {
  const signedIn = Boolean(useSession().data);
  const phone = useMediaQuery("(max-width: 639px)");
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-on-accent"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-2 px-4 sm:gap-4">
          <NavLink
            to="/"
            aria-label="Serve Analyzer home"
            className="flex shrink-0 items-center gap-2 font-semibold tracking-tight"
          >
            <svg viewBox="0 0 24 24" className="size-6 text-accent" aria-hidden>
              <circle cx="12" cy="12" r="10" fill="currentColor" />
              <path d="M4.5 6.5c3.5 2 3.5 9 0 11M19.5 6.5c-3.5 2-3.5 9 0 11" fill="none" stroke="var(--bg)" strokeWidth="1.6" />
            </svg>
            <span className="hidden md:inline">Serve Analyzer</span>
          </NavLink>
          {signedIn && !phone && <MainNav phone={false} />}
          <div className="ml-auto flex items-center gap-1 sm:gap-3">
            {USE_MOCKS && (
              <span className="whitespace-nowrap rounded-full border border-warn/40 px-2 py-0.5 text-xs font-medium text-warn">
                Mock data
              </span>
            )}
            <HelpButton />
            <ThemeToggle />
            {signedIn && <NotificationBell />}
            <AccountMenu />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      {signedIn && phone && <MainNav phone />}
      <footer className={`border-t border-border ${signedIn && phone ? "pb-20" : ""}`}>
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
