import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation } from "react-router";

import { useMarkNotificationsRead, useNotificationCount, useNotifications } from "../api/notifications";
import type { Notification } from "../api/types";
import { Avatar } from "./Avatar";

const TEXT: Record<Notification["kind"], string> = {
  new_follower: "started following you",
  followed_back: "followed you back. You're friends now",
  serve_received: "sent you a serve",
};

function linkFor(n: Notification): string {
  if (n.kind === "serve_received") return "/messages/received";
  return n.person?.username ? `/u/${n.person.username}` : "/friends";
}

function when(iso: string): string {
  const minutes = Math.round((Date.now() - Date.parse(iso)) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** A bell with the unread count, opening the latest notifications. Opening marks them read. */
export function NotificationBell() {
  const count = useNotificationCount().data ?? 0;
  const [open, setOpen] = useState(false);
  const list = useNotifications(open);
  const markRead = useMarkNotificationsRead();
  const location = useLocation();
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => setOpen(false), [location.pathname]);
  const mark = markRead.mutate;
  useEffect(() => {
    if (open && count > 0) mark();
  }, [open, count, mark]);
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

  const items = list.data ?? [];
  return (
    <div className="relative">
      <button
        ref={button}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={id}
        aria-label={count ? `Notifications, ${count} new` : "Notifications"}
        className="relative grid size-9 place-items-center rounded-lg border border-border text-ink-muted hover:text-ink"
      >
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
          <path d="M6 9a6 6 0 1 1 12 0c0 5 2 6.5 2 6.5H4S6 14 6 9ZM10 19a2 2 0 0 0 4 0" />
        </svg>
        {count > 0 && (
          <span aria-hidden className="absolute -right-1 -top-1 grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-4 text-on-accent">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>
      {open && (
        <div ref={panel} id={id} className="absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-surface p-1.5 shadow-xl">
          <p className="px-3 pb-1 pt-1.5 text-sm font-semibold">Notifications</p>
          {list.isPending ? (
            <p className="px-3 py-2 text-sm text-ink-muted">Loading…</p>
          ) : list.isError ? (
            <p role="alert" className="px-3 py-2 text-sm text-bad">We couldn't load your notifications.</p>
          ) : items.length === 0 ? (
            <p className="px-3 py-2 text-sm text-ink-muted">Nothing new. New followers and serves sent to you show here.</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {items.map((n) => (
                <li key={n.id}>
                  <Link to={linkFor(n)} className={`flex items-start gap-3 rounded-lg px-3 py-2 text-sm hover:bg-surface-2 ${n.read ? "" : "bg-accent/5"}`}>
                    <Avatar url={n.person?.avatar_url} name={n.person?.display_name ?? n.person?.username} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="font-medium">{n.person?.display_name ?? (n.person?.username ? `@${n.person.username}` : "Someone")}</span>{" "}
                      {TEXT[n.kind]}
                      <time dateTime={n.created_at} className="block text-xs text-ink-muted">{when(n.created_at)}</time>
                    </span>
                    {!n.read && <span className="sr-only">(new)</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
