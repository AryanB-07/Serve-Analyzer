import { useId, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../../api/client";
import { useAcceptRequest, useBlock, usePerson, useRemoveConnection, useSendRequest } from "../../api/friends";
import type { Person } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { displayName, friendsErrorMessage } from "./FriendsPage";

const primary = "rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50";
const secondary = "rounded-lg border border-border px-4 py-2 text-sm font-semibold hover:bg-surface-2 disabled:opacity-50";
const when = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });

function Actions({ person }: { person: Person }) {
  const send = useSendRequest();
  const accept = useAcceptRequest();
  const remove = useRemoveConnection();
  const [confirmUnfriend, setConfirmUnfriend] = useState(false);
  const busy = send.isPending || accept.isPending || remove.isPending;
  const error = send.error ?? accept.error ?? remove.error;
  const name = displayName(person);

  let actions;
  switch (person.relationship) {
    case "self":
      actions = <Link to="/profile" className={secondary}>This is you: open your profile</Link>;
      break;
    case "none":
      actions = person.can_request ? (
        <button type="button" disabled={busy} onClick={() => send.mutate(person.username!)} className={primary}>
          {send.isPending ? "Sending…" : "Add friend"}
        </button>
      ) : (
        <p className="text-sm text-ink-muted">{name} isn't accepting friend requests.</p>
      );
      break;
    case "requested":
      actions = (
        <>
          <p className="text-sm text-ink-muted">Request sent.</p>
          <button type="button" disabled={busy} onClick={() => remove.mutate(person.connection_id!)} className={secondary}>Cancel request</button>
        </>
      );
      break;
    case "incoming":
      actions = (
        <>
          <p className="w-full text-sm">{name} wants to be friends.</p>
          <button type="button" disabled={busy} onClick={() => accept.mutate(person.connection_id!)} className={primary}>Accept</button>
          <button type="button" disabled={busy} onClick={() => remove.mutate(person.connection_id!)} className={secondary}>Decline</button>
        </>
      );
      break;
    case "friends":
      actions = confirmUnfriend ? (
        <>
          <p className="w-full text-sm">Remove {name} from your friends? They won't be told.</p>
          <button type="button" disabled={busy} onClick={() => remove.mutate(person.connection_id!)} className={secondary}>Remove friend</button>
          <button type="button" onClick={() => setConfirmUnfriend(false)} className="px-2 text-sm text-ink-muted hover:text-ink">Cancel</button>
        </>
      ) : (
        <>
          <p className="text-sm text-good">Friends{person.friends_since ? ` since ${when(person.friends_since)}` : ""}</p>
          <button type="button" onClick={() => setConfirmUnfriend(true)} className="text-sm text-ink-muted hover:text-ink">Remove friend…</button>
        </>
      );
      break;
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-center gap-3 sm:justify-start">{actions}</div>
      {error && <p role="alert" className="text-sm text-bad">{friendsErrorMessage(error)}</p>}
    </div>
  );
}

function BlockControl({ person, onBlocked }: { person: Person; onBlocked: (name: string) => void }) {
  const id = useId();
  const block = useBlock();
  const [open, setOpen] = useState(false);
  const name = displayName(person);
  return open ? (
    <div role="group" aria-labelledby={id} className="space-y-2 rounded-xl border border-bad/40 p-4">
      <p id={id} className="text-sm">
        Block {name}? Any request or friendship between you ends. They won't be able to find you, and won't be told.
      </p>
      {block.error && <p role="alert" className="text-sm text-bad">{friendsErrorMessage(block.error)}</p>}
      <div className="flex gap-2">
        <button type="button" disabled={block.isPending} onClick={() => block.mutate(person.username!, { onSuccess: () => onBlocked(name) })}
          className="rounded-lg bg-bad px-4 py-2 text-sm font-semibold text-on-accent disabled:opacity-50">
          {block.isPending ? "Blocking…" : `Block ${name}`}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-3 text-sm text-ink-muted hover:text-ink">Cancel</button>
      </div>
    </div>
  ) : (
    <button type="button" onClick={() => setOpen(true)} className="text-sm text-ink-muted hover:text-bad">Block {name}…</button>
  );
}

export function PersonPage() {
  const { username = "" } = useParams();
  const person = usePerson(username);
  const p = person.data;
  // Once blocked, they're hidden from you too, so their page would read "no one has that
  // username": say what happened instead.
  const [blocked, setBlocked] = useState<string | null>(null);

  if (blocked) {
    return (
      <div role="status" className="mx-auto max-w-lg space-y-3 py-10 text-center">
        <h1 className="text-2xl font-semibold">You've blocked {blocked}</h1>
        <p className="text-ink-muted">They can't find you or send you requests, and they haven't been told.</p>
        <p className="text-sm">
          <Link to="/friends" className="font-medium text-accent hover:underline">Back to Friends</Link>
          <span className="text-ink-muted"> · </span>
          <Link to="/settings#blocked" className="font-medium text-accent hover:underline">Blocked people</Link>
        </p>
      </div>
    );
  }
  if (person.isError) {
    const missing = person.error instanceof ApiError && person.error.status === 404;
    return (
      <div className="mx-auto max-w-lg space-y-3 py-10 text-center">
        <h1 className="text-2xl font-semibold">{missing ? "No one has that username" : "We couldn't load this page"}</h1>
        <p className="text-ink-muted">{missing ? `Check the spelling of @${username}.` : "Check your connection and try again."}</p>
        <Link to="/friends" className="inline-block font-medium text-accent hover:underline">Back to Friends</Link>
      </div>
    );
  }
  if (!p) return <p className="text-ink-muted">Loading…</p>;

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 py-4">
      <section aria-label={displayName(p)} className="rounded-2xl border border-border bg-surface p-6">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
          <Avatar url={p.avatar_url} name={p.display_name ?? p.username} size="lg" />
          <div className="min-w-0 flex-1 space-y-3 text-center sm:text-left">
            <div>
              <h1 className="break-words text-2xl font-semibold tracking-tight">{displayName(p)}</h1>
              {p.display_name && <p className="text-ink-muted">@{p.username}</p>}
            </div>
            {p.bio && <p className="whitespace-pre-line break-words">{p.bio}</p>}
            {p.relationship !== "friends" && p.relationship !== "self" && (
              <p className="text-xs text-ink-muted">Friends see more of each other's profile.</p>
            )}
            <Actions person={p} />
          </div>
        </div>
      </section>
      {p.relationship !== "self" && <BlockControl person={p} onBlocked={setBlocked} />}
    </div>
  );
}
