import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useCreatePost, usePostsBy } from "../../api/posts";
import type { AnalysisSummary, Visibility } from "../../api/types";
import { friendsErrorMessage } from "../friends/FriendsPage";
import { PostList } from "./PostCard";
import { VisibilityChoice } from "./PostPage";

const MAX_CAPTION = 500;

/** On your own serve's results: post it, with a caption, for friends (the default) or everyone. */
export function CreatePost({ summary }: { summary: AnalysisSummary }) {
  const id = useId();
  const create = useCreatePost();
  const [open, setOpen] = useState(false);
  const [caption, setCaption] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("friends");
  const [posted, setPosted] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ analysis_id: summary.id, caption: caption.trim() || null, visibility }, {
      onSuccess: (post) => {
        setPosted(post.id);
        setOpen(false);
        setCaption("");
      },
    });
  }

  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2">
        Post this serve
      </button>
      {posted && (
        <p role="status" className="mt-1 text-sm">
          Posted. <Link to={`/p/${posted}`} className="text-accent underline">View your post</Link>
        </p>
      )}
      {open && (
        <form onSubmit={submit} aria-label="Post this serve"
          className="absolute right-0 top-full z-30 mt-2 w-80 max-w-[calc(100vw-2rem)] space-y-3 rounded-xl border border-border bg-surface p-4 shadow-xl">
          <div className="space-y-1">
            <label htmlFor={`${id}-caption`} className="text-sm font-medium">Caption <span className="text-ink-muted">(optional)</span></label>
            <textarea id={`${id}-caption`} value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={MAX_CAPTION} rows={3}
              placeholder="What were you working on?"
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40" />
          </div>
          <VisibilityChoice value={visibility} onChange={setVisibility} name={`${id}-visibility`} />
          <p className="text-xs text-ink-muted">The post shows the skeleton video and scores, never your note or the file's name.</p>
          {create.error && <p role="alert" className="text-sm text-bad">{friendsErrorMessage(create.error)}</p>}
          <div className="flex gap-2">
            <button type="submit" disabled={create.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50">
              {create.isPending ? "Posting…" : "Post"}
            </button>
            <button type="button" onClick={() => setOpen(false)} className="px-3 text-sm text-ink-muted hover:text-ink">Cancel</button>
          </div>
        </form>
      )}
    </div>
  );
}

/** The posts section on a profile: yours, or someone else's that you can see. */
export function PostsSection({ username, title, empty }: { username: string; title: string; empty: string }) {
  const id = useId();
  const posts = usePostsByList(username);
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h2 id={id} className="text-lg font-semibold">{title}</h2>
      {posts.isError ? (
        <p role="alert" className="text-sm text-bad">We couldn't load the posts.</p>
      ) : posts.isPending ? (
        <p className="text-sm text-ink-muted">Loading…</p>
      ) : (
        <PostList posts={posts.items} hasMore={posts.hasNextPage} loadingMore={posts.isFetchingNextPage}
          onMore={() => posts.fetchNextPage()} empty={empty} />
      )}
    </section>
  );
}

function usePostsByList(username: string) {
  const query = usePostsBy(username);
  return { ...query, items: query.data?.pages.flatMap((p) => p.items) ?? [] };
}
