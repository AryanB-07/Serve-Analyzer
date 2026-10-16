import type { SyntheticEvent } from "react";
import { Link } from "react-router";

import { useLike } from "../../api/posts";
import type { Post } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { bandOf } from "../../lib/score";
import { displayName } from "../friends/FriendsPage";
import { SCORE_TEXT } from "../results/MetricCards";

export function when(iso: string): string {
  const minutes = Math.round((Date.now() - Date.parse(iso)) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}

export function VisibilityBadge({ visibility }: { visibility: Post["visibility"] }) {
  return (
    <span className="rounded-full border border-border px-2 py-0.5 text-xs text-ink-muted"
      title={visibility === "public" ? "Everyone signed in can see this" : "Only friends can see this"}>
      {visibility === "public" ? "Public" : "Friends"}
    </span>
  );
}

export function LikeButton({ post }: { post: Post }) {
  const like = useLike(post);
  const name = displayName(post.author);
  return (
    <button
      type="button"
      onClick={() => like.mutate(!post.liked_by_you)}
      aria-pressed={post.liked_by_you}
      aria-label={`${post.liked_by_you ? "Unlike" : "Like"} ${name}'s post, ${post.like_count} ${post.like_count === 1 ? "like" : "likes"}`}
      className={`inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm hover:bg-surface-2 ${post.liked_by_you ? "text-bad" : "text-ink-muted"}`}
    >
      <svg viewBox="0 0 24 24" className="size-5" fill={post.liked_by_you ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" aria-hidden>
        <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" />
      </svg>
      <span className="tabular">{post.like_count}</span>
    </button>
  );
}

/** One video at a time: starting one pauses any other that's playing. */
function pauseOthers(event: SyntheticEvent<HTMLVideoElement>) {
  document.querySelectorAll("video").forEach((v) => {
    if (v !== event.currentTarget && !v.paused) v.pause();
  });
}

/**
 * A post: who, when and for whom; the serve's skeleton video (it loads only when played, so a
 * page of posts doesn't fetch every video); the caption and score; likes and comments.
 */
export function PostCard({ post, linkToPost = true }: { post: Post; linkToPost?: boolean }) {
  const name = displayName(post.author);
  const score = post.overall_score;
  return (
    <article aria-label={`${name}'s post`} className="overflow-hidden rounded-xl border border-border bg-surface">
      <header className="flex items-center gap-3 p-3">
        <Avatar url={post.author.avatar_url} name={post.author.display_name ?? post.author.username} size="sm" />
        <div className="min-w-0 flex-1">
          {post.author.username ? (
            <Link to={`/u/${post.author.username}`} className="block truncate text-sm font-medium hover:underline">{name}</Link>
          ) : (
            <p className="truncate text-sm font-medium">{name}</p>
          )}
          <p className="text-xs text-ink-muted"><time dateTime={post.created_at}>{when(post.created_at)}</time></p>
        </div>
        <VisibilityBadge visibility={post.visibility} />
      </header>
      <video
        src={post.video_url}
        poster={post.thumbnail_url}
        preload="none"
        controls
        playsInline
        className="aspect-video w-full bg-black object-contain"
        aria-label={`${name}'s serve`}
        onPlay={pauseOthers}
      />
      <div className="space-y-2 p-3">
        {post.caption && <p className="whitespace-pre-line break-words text-sm">{post.caption}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <LikeButton post={post} />
          {linkToPost ? (
            <Link to={`/p/${post.id}`} className="rounded-lg px-2 py-1 text-sm text-ink-muted hover:bg-surface-2 hover:text-ink">
              {post.comment_count} {post.comment_count === 1 ? "comment" : "comments"}
            </Link>
          ) : (
            <span className="px-2 py-1 text-sm text-ink-muted">{post.comment_count} {post.comment_count === 1 ? "comment" : "comments"}</span>
          )}
          {score != null && (
            <span className="ml-auto text-sm text-ink-muted">
              Serve score <span className={`tabular font-semibold ${SCORE_TEXT[bandOf(score)]}`}>{score}</span>
            </span>
          )}
        </div>
      </div>
    </article>
  );
}

/** Posts, a page at a time. */
export function PostList({ posts, hasMore, loadingMore, onMore, empty }: {
  posts: Post[];
  hasMore: boolean;
  loadingMore: boolean;
  onMore: () => void;
  empty: string;
}) {
  if (posts.length === 0) return <p className="py-6 text-center text-sm text-ink-muted">{empty}</p>;
  return (
    <div className="space-y-4">
      {posts.map((p) => <PostCard key={p.id} post={p} />)}
      {hasMore && (
        <div className="text-center">
          <button type="button" onClick={onMore} disabled={loadingMore}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-surface-2 disabled:opacity-50">
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
