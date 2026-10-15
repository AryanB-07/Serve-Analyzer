import { Link } from "react-router";

import { useConversations } from "../../api/messages";
import { Avatar } from "../../components/Avatar";
import { displayName } from "../friends/FriendsPage";

export function shortWhen(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString(undefined, { timeStyle: "short" })
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function MessagesPage() {
  const list = useConversations();
  const items = list.data;
  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 py-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Messages</h1>
        <p className="text-ink-muted">Message your friends from their page on Friends.</p>
      </header>
      {list.isError ? (
        <div role="alert" className="space-y-2">
          <p>We couldn't load your messages.</p>
          <button type="button" onClick={() => list.refetch()} className="rounded-lg border border-border px-4 py-2">Try again</button>
        </div>
      ) : !items ? (
        <p className="text-ink-muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center">
          <p className="font-medium">No messages yet</p>
          <p className="text-ink-muted">Open a friend's page and choose Message.</p>
          <Link to="/friends" className="mt-2 inline-block text-sm font-medium text-accent hover:underline">Go to Friends</Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map((c) => {
            const name = c.person ? displayName(c.person) : "Deleted account";
            const last = c.last_message;
            const preview = !last ? "" : last.deleted ? "Message deleted" : `${last.from_you ? "You: " : ""}${last.text ?? ""}`;
            return (
              <li key={c.id}>
                <Link
                  to={`/messages/${c.id}`}
                  className={`flex items-center gap-3 rounded-xl border p-3 hover:bg-surface-2 ${c.unread ? "border-accent/60 bg-accent/5" : "border-border bg-surface"}`}
                >
                  <Avatar url={c.person?.avatar_url} name={c.person?.display_name ?? c.person?.username} size="md" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className={`truncate ${c.unread ? "font-semibold" : "font-medium"}`}>{name}</p>
                      {last && <time dateTime={last.at} className="shrink-0 text-xs text-ink-muted">{shortWhen(last.at)}</time>}
                    </div>
                    <p className={`truncate text-sm ${c.unread ? "text-ink" : "text-ink-muted"} ${last?.deleted ? "italic" : ""}`}>{preview}</p>
                  </div>
                  {c.unread > 0 && (
                    <span className="grid min-w-5 shrink-0 place-items-center rounded-full bg-accent px-1.5 text-xs font-bold leading-5 text-on-accent">
                      {c.unread}
                      <span className="sr-only"> unread</span>
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
