import { useEffect, useId, useRef } from "react";
import { Link, useSearchParams } from "react-router";

import { useFeed } from "../../api/posts";
import type { FeedTab } from "../../api/types";
import { friendsErrorMessage } from "../friends/FriendsPage";
import { PostCard } from "./PostCard";

const TABS: { key: FeedTab; label: string }[] = [
  { key: "public", label: "Public" },
  { key: "friends", label: "Friends" },
];

function Placeholder() {
  return (
    <div aria-hidden className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex items-center gap-3 p-3">
        <div className="size-8 rounded-full bg-surface-2" />
        <div className="h-3 w-32 rounded bg-surface-2" />
      </div>
      <div className="aspect-video w-full bg-surface-2" />
      <div className="h-10" />
    </div>
  );
}

function Empty({ tab }: { tab: FeedTab }) {
  return (
    <div className="space-y-2 rounded-xl border border-dashed border-border p-8 text-center">
      {tab === "friends" ? (
        <>
          <p className="font-medium">No posts from friends yet</p>
          <p className="text-sm text-ink-muted">
            Friends are people you follow who follow you back. <Link to="/friends" className="font-medium text-accent hover:underline">Find people to follow</Link>.
          </p>
        </>
      ) : (
        <>
          <p className="font-medium">No public posts yet</p>
          <p className="text-sm text-ink-muted">
            Post one of <Link to="/serves" className="font-medium text-accent hover:underline">your serves</Link> for everyone to be the first.
          </p>
        </>
      )}
    </div>
  );
}

/** A tab's posts. The next page loads as you near the end, or with the button where that can't be watched. */
function FeedPanel({ tab }: { tab: FeedTab }) {
  const feed = useFeed(tab);
  const end = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = feed;

  useEffect(() => {
    const target = end.current;
    if (!target || !hasNextPage || isFetchingNextPage || isFetchNextPageError || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) fetchNextPage();
    }, { rootMargin: "600px 0px" });
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage]);

  if (feed.isPending) {
    return (
      <div aria-busy="true" className="space-y-4">
        <p className="sr-only" role="status">Loading posts…</p>
        <Placeholder />
        <Placeholder />
      </div>
    );
  }
  if (feed.isError && !feed.data) {
    return (
      <div role="alert" className="space-y-3 rounded-xl border border-border p-6 text-center">
        <p className="font-medium">We couldn't load the feed</p>
        <p className="text-sm text-ink-muted">{friendsErrorMessage(feed.error)}</p>
        <button type="button" onClick={() => feed.refetch()} className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-surface-2">
          Try again
        </button>
      </div>
    );
  }
  const posts = feed.data.pages.flatMap((p) => p.items);
  if (posts.length === 0) return <Empty tab={tab} />;
  return (
    <div className="space-y-4">
      {posts.map((p) => <PostCard key={p.id} post={p} />)}
      <div ref={end} className="py-2 text-center">
        {isFetchNextPageError ? (
          <div role="alert" className="space-y-2">
            <p className="text-sm text-bad">We couldn't load more posts.</p>
            <button type="button" onClick={() => fetchNextPage()} className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-surface-2">
              Try again
            </button>
          </div>
        ) : hasNextPage ? (
          <button type="button" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-surface-2 disabled:opacity-50">
            {isFetchingNextPage ? "Loading…" : "Load more"}
          </button>
        ) : (
          <p className="text-sm text-ink-muted">You're all caught up.</p>
        )}
      </div>
    </div>
  );
}

export function FeedPage() {
  const id = useId();
  const [params, setParams] = useSearchParams();
  const tab: FeedTab = params.get("tab") === "friends" ? "friends" : "public";
  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-2xl font-semibold">Feed</h1>
        <Link to="/serves" className="text-sm font-medium text-accent hover:underline">Post a serve</Link>
      </div>
      <div role="tablist" aria-label="Feed" className="flex gap-1 rounded-xl border border-border bg-surface p-1">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" id={`${id}-${t.key}`} aria-selected={tab === t.key} aria-controls={`${id}-panel`}
            onClick={() => setParams(t.key === "public" ? {} : { tab: t.key }, { replace: true })}
            className={`flex-1 rounded-lg px-2 py-1.5 text-sm font-medium ${tab === t.key ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"}`}>
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${tab}`}>
        <FeedPanel key={tab} tab={tab} />
      </div>
    </div>
  );
}
