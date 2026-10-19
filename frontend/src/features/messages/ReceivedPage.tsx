import { Link } from "react-router";

import { useReceived } from "../../api/messages";
import type { ReceivedServe } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { displayName } from "../friends/FriendsPage";
import { when } from "../posts/PostCard";
import { MessagesHeader } from "./MessagesPage";
import { ServeCard } from "./ServeCard";

function ReceivedItem({ item }: { item: ReceivedServe }) {
  const name = displayName(item.sender);
  const open = item.serve.available;
  const isNew = !item.seen && open;
  return (
    <li className={`space-y-2 rounded-xl border p-3 ${isNew ? "border-accent/60 bg-accent/5" : "border-border bg-surface"} ${open ? "" : "opacity-75"}`}>
      <div className="flex items-center gap-3">
        <Avatar url={item.sender.avatar_url} name={item.sender.display_name ?? item.sender.username} size="sm" />
        <p className="min-w-0 flex-1 text-sm">
          {item.sender.username ? (
            <Link to={`/u/${item.sender.username}`} className="font-medium hover:underline">{name}</Link>
          ) : <span className="font-medium">{name}</span>}{" "}
          sent you a serve · <time dateTime={item.sent_at} className="text-ink-muted">{when(item.sent_at)}</time>
        </p>
        {isNew ? (
          <span className="shrink-0 rounded-full bg-accent px-2 py-0.5 text-xs font-bold text-on-accent">New</span>
        ) : open ? (
          <span className="shrink-0 text-xs text-ink-muted">Seen</span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ServeCard serve={item.serve} mine={false} />
        <Link to={`/messages/${item.conversation_id}`} className="text-sm font-medium text-accent hover:underline">
          Open conversation
        </Link>
      </div>
    </li>
  );
}

/** Serves friends sent you: who, when, and whether you've opened each one yet. */
export function ReceivedPage() {
  const list = useReceived();
  const items = list.data?.pages.flatMap((p) => p.items);
  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 py-4">
      <MessagesHeader hint="Serves your friends sent you. Opening one marks it seen." />
      {list.isError && !items ? (
        <div role="alert" className="space-y-2">
          <p>We couldn't load the serves sent to you.</p>
          <button type="button" onClick={() => list.refetch()} className="rounded-lg border border-border px-4 py-2">Try again</button>
        </div>
      ) : !items ? (
        <p className="text-ink-muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center">
          <p className="font-medium">No serves yet</p>
          <p className="text-ink-muted">When a friend sends you one of their serves, it shows up here.</p>
        </div>
      ) : (
        <>
          <ul aria-label="Received serves" className="space-y-3">
            {items.map((item) => <ReceivedItem key={item.message_id} item={item} />)}
          </ul>
          {list.hasNextPage && (
            <div className="text-center">
              <button type="button" onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage}
                className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-surface-2 disabled:opacity-50">
                {list.isFetchingNextPage ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
