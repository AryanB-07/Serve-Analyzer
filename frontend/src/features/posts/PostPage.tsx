import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError } from "../../api/client";
import { useAddComment, useComments, useDeleteComment, useDeletePost, useEditPost, usePost } from "../../api/posts";
import type { Comment, Post, Visibility } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { displayName, friendsErrorMessage } from "../friends/FriendsPage";
import { ReportForm } from "../messages/ReportForm";
import { PostCard, when } from "./PostCard";

const MAX_CAPTION = 500;
const MAX_COMMENT = 1000;

export function VisibilityChoice({ value, onChange, name }: { value: Visibility; onChange: (v: Visibility) => void; name: string }) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">Who can see it</legend>
      {([["friends", "Friends", "Only people who follow you and you follow back."],
        ["public", "Public", "Everyone signed in to Serve Analyzer."]] as const).map(([v, label, hint]) => (
        <label key={v} className="flex cursor-pointer items-start gap-2 text-sm">
          <input type="radio" name={name} checked={value === v} onChange={() => onChange(v)} className="mt-0.5 accent-[var(--accent)]" />
          <span><span className="font-medium">{label}</span> <span className="text-ink-muted">· {hint}</span></span>
        </label>
      ))}
    </fieldset>
  );
}

function OwnerControls({ post }: { post: Post }) {
  const id = useId();
  const navigate = useNavigate();
  const edit = useEditPost(post.id);
  const remove = useDeletePost();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [caption, setCaption] = useState(post.caption ?? "");
  const [visibility, setVisibility] = useState<Visibility>(post.visibility);

  function save(event: FormEvent) {
    event.preventDefault();
    edit.mutate({ caption, visibility }, { onSuccess: () => setEditing(false) });
  }

  if (editing) {
    return (
      <form onSubmit={save} aria-label="Edit post" className="space-y-3 rounded-xl border border-border bg-surface p-4">
        <label htmlFor={`${id}-caption`} className="text-sm font-medium">Caption</label>
        <textarea id={`${id}-caption`} value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={MAX_CAPTION} rows={3}
          className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40" />
        <VisibilityChoice value={visibility} onChange={setVisibility} name={`${id}-visibility`} />
        {edit.error && <p role="alert" className="text-sm text-bad">{friendsErrorMessage(edit.error)}</p>}
        <div className="flex gap-2">
          <button type="submit" disabled={edit.isPending} className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent disabled:opacity-50">
            {edit.isPending ? "Saving…" : "Save"}
          </button>
          <button type="button" onClick={() => setEditing(false)} className="px-3 text-sm text-ink-muted hover:text-ink">Cancel</button>
        </div>
      </form>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <button type="button" onClick={() => setEditing(true)} className="font-medium text-accent hover:underline">Edit post</button>
      {confirming ? (
        <>
          <span>Delete this post, with its likes and comments? Your serve stays in My Serves.</span>
          <button type="button" disabled={remove.isPending}
            onClick={async () => {
              // Awaited rather than an onSuccess callback, which doesn't run if this unmounts first.
              try {
                await remove.mutateAsync(post.id);
                navigate("/profile", { replace: true });
              } catch {
                // shown from remove.error
              }
            }}
            className="font-semibold text-bad hover:underline">Delete post</button>
          <button type="button" onClick={() => setConfirming(false)} className="text-ink-muted hover:text-ink">Cancel</button>
        </>
      ) : (
        <button type="button" onClick={() => setConfirming(true)} className="text-ink-muted hover:text-bad">Delete…</button>
      )}
      {remove.error && <p role="alert" className="w-full text-sm text-bad">{friendsErrorMessage(remove.error)}</p>}
    </div>
  );
}

function CommentItem({ comment }: { comment: Comment }) {
  const remove = useDeleteComment();
  const [confirming, setConfirming] = useState(false);
  const [reporting, setReporting] = useState(false);
  const name = displayName(comment.author);
  return (
    <li className="space-y-1">
      <div className="flex items-start gap-3">
        <Avatar url={comment.author.avatar_url} name={comment.author.display_name ?? comment.author.username} size="sm" />
        <div className="min-w-0 flex-1">
          <p className="text-sm">
            {comment.author.username ? (
              <Link to={`/u/${comment.author.username}`} className="font-medium hover:underline">{name}</Link>
            ) : <span className="font-medium">{name}</span>}{" "}
            <time dateTime={comment.created_at} className="text-xs text-ink-muted">{when(comment.created_at)}</time>
          </p>
          <p className="whitespace-pre-line break-words text-sm">{comment.body}</p>
          <div className="mt-0.5 flex gap-3 text-xs text-ink-muted">
            {comment.can_delete && !confirming && (
              <button type="button" onClick={() => setConfirming(true)} className="hover:text-ink" aria-label={`Delete ${name}'s comment`}>Delete</button>
            )}
            {confirming && (
              <>
                <span>Delete this comment?</span>
                <button type="button" disabled={remove.isPending} onClick={() => remove.mutate(comment.id)} className="font-semibold text-bad hover:underline">
                  Yes, delete it
                </button>
                <button type="button" onClick={() => setConfirming(false)} className="hover:text-ink">Keep</button>
              </>
            )}
            {!comment.can_delete && comment.author.username && !reporting && (
              <button type="button" onClick={() => setReporting(true)} className="hover:text-ink" aria-label={`Report ${name}'s comment`}>Report</button>
            )}
          </div>
        </div>
      </div>
      {reporting && comment.author.username && (
        <div className="pl-11">
          <ReportForm username={comment.author.username} name={name} commentId={comment.id} onDone={() => setReporting(false)} />
        </div>
      )}
    </li>
  );
}

function Comments({ post }: { post: Post }) {
  const id = useId();
  const list = useComments(post.id);
  const add = useAddComment(post.id);
  const [text, setText] = useState("");
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!text.trim() || text.trim().length > MAX_COMMENT) return;
    add.mutate(text.trim(), { onSuccess: () => setText("") });
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="space-y-4">
      <h2 id={`${id}-title`} className="text-lg font-semibold">Comments</h2>
      {list.isPending ? (
        <p className="text-sm text-ink-muted">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-ink-muted">No comments yet.</p>
      ) : (
        <ol className="space-y-4">{items.map((c) => <CommentItem key={c.id} comment={c} />)}</ol>
      )}
      {list.hasNextPage && (
        <button type="button" onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage}
          className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-surface-2 disabled:opacity-50">
          {list.isFetchingNextPage ? "Loading…" : "Show more comments"}
        </button>
      )}
      <form onSubmit={submit} aria-label="Add a comment" className="space-y-1">
        <div className="flex items-end gap-2">
          <label htmlFor={`${id}-text`} className="sr-only">Comment</label>
          <textarea id={`${id}-text`} value={text} onChange={(e) => { setText(e.target.value); add.reset(); }} onKeyDown={onKeyDown}
            rows={Math.min(4, Math.max(1, text.split("\n").length))} placeholder="Add a comment"
            className="min-h-11 w-full resize-none rounded-2xl border border-border bg-bg px-4 py-2.5 text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40" />
          <button type="submit" disabled={!text.trim() || text.trim().length > MAX_COMMENT || add.isPending}
            className="h-11 shrink-0 rounded-full bg-accent px-5 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50">
            {add.isPending ? "Posting…" : "Post"}
          </button>
        </div>
        {text.length > MAX_COMMENT - 100 && <p className="px-2 text-xs text-ink-muted">{text.trim().length}/{MAX_COMMENT}</p>}
        {add.error && <p role="alert" className="px-2 text-sm text-bad">{friendsErrorMessage(add.error)}</p>}
      </form>
    </section>
  );
}

export function PostPage() {
  const { id = "" } = useParams();
  const post = usePost(id);
  const [reporting, setReporting] = useState(false);
  const p = post.data;
  if (post.isError) {
    const missing = post.error instanceof ApiError && post.error.status === 404;
    return (
      <div className="mx-auto max-w-lg space-y-3 py-10 text-center">
        <h1 className="text-2xl font-semibold">{missing ? "Post not found" : "We couldn't load this post"}</h1>
        <p className="text-ink-muted">{missing ? "It may have been deleted, or it's only for the author's friends." : "Check your connection and try again."}</p>
        <Link to="/friends" className="font-medium text-accent hover:underline">Back to Friends</Link>
      </div>
    );
  }
  if (!p) return <p className="text-ink-muted">Loading…</p>;
  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 py-4">
      <h1 className="sr-only">{displayName(p.author)}'s post</h1>
      <PostCard post={p} linkToPost={false} />
      {p.is_yours ? (
        <OwnerControls post={p} />
      ) : p.author.username && (
        reporting ? (
          <ReportForm username={p.author.username} name={displayName(p.author)} postId={p.id} onDone={() => setReporting(false)} />
        ) : (
          <button type="button" onClick={() => setReporting(true)} className="text-sm text-ink-muted hover:text-bad">Report this post…</button>
        )
      )}
      <Comments post={p} />
    </div>
  );
}
