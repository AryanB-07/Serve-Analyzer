import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { useAcceptRequest, useConnections, useRemoveConnection } from "../../api/friends";
import { useProfile } from "../../api/profile";
import type { Connection, PersonSummary } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { normaliseUsername, usernameProblem } from "../../lib/username";
import { authErrorMessage } from "../auth/AuthForm";

export function friendsErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status > 0 && error.status < 500) return error.message;
  return authErrorMessage(error);
}

export function displayName(person: PersonSummary): string {
  return person.display_name ?? (person.username ? `@${person.username}` : "Someone");
}

/** One person in a list: picture, name and @username (a link to their page), and actions. */
export function PersonRow({ person, detail, children }: { person: PersonSummary; detail?: ReactNode; children?: ReactNode }) {
  const name = displayName(person);
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface p-3">
      <Avatar url={person.avatar_url} name={person.display_name ?? person.username} size="md" />
      <div className="min-w-0 flex-1">
        {person.username ? (
          <Link to={`/u/${person.username}`} className="block truncate font-medium hover:underline">{name}</Link>
        ) : (
          <p className="truncate font-medium">{name}</p>
        )}
        {person.username && person.display_name && <p className="truncate text-sm text-ink-muted">@{person.username}</p>}
        {detail && <p className="text-xs text-ink-muted">{detail}</p>}
      </div>
      {/* Phones: the buttons go under the name, so a long name isn't cut short. */}
      {children && <div className="flex w-full shrink-0 flex-wrap justify-end gap-2 sm:w-auto">{children}</div>}
    </li>
  );
}

const small = "rounded-lg px-3 py-1.5 text-sm font-semibold disabled:opacity-50";
const when = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });

function FindSomeone() {
  const id = useId();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const name = normaliseUsername(value);
    const issue = name ? usernameProblem(name) : "Enter their username.";
    if (issue && issue !== "That username is reserved.") return setProblem(issue);
    navigate(`/u/${name}`);
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Find someone" className="space-y-2 rounded-xl border border-border bg-surface p-4">
      <label htmlFor={`${id}-username`} className="text-sm font-medium">Find someone by their username</label>
      <div className="flex gap-2">
        <div className="flex flex-1 items-center rounded-lg border border-border bg-bg focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/40">
          <span className="pl-3 text-ink-muted" aria-hidden>@</span>
          <input
            id={`${id}-username`}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setProblem(null);
            }}
            autoCapitalize="none"
            spellCheck={false}
            autoComplete="off"
            aria-describedby={problem ? `${id}-problem` : undefined}
            className="w-full rounded-lg bg-transparent py-2 pl-1 pr-3 text-ink focus:outline-none"
          />
        </div>
        <button type="submit" className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong">
          Find
        </button>
      </div>
      {problem && <p id={`${id}-problem`} role="alert" className="text-sm text-bad">{problem}</p>}
      <p className="text-xs text-ink-muted">Only exact usernames work: nobody is listed or suggested.</p>
    </form>
  );
}

function Incoming({ item }: { item: Connection }) {
  const accept = useAcceptRequest();
  const decline = useRemoveConnection();
  const busy = accept.isPending || decline.isPending;
  const error = accept.error ?? decline.error;
  return (
    <>
      <PersonRow person={item.person} detail={`Asked ${when(item.created_at)}`}>
        <button type="button" disabled={busy} onClick={() => accept.mutate(item.id)} className={`${small} bg-accent text-on-accent hover:bg-accent-strong`}
          aria-label={`Accept ${displayName(item.person)}'s request`}>
          Accept
        </button>
        <button type="button" disabled={busy} onClick={() => decline.mutate(item.id)} className={`${small} border border-border hover:bg-surface-2`}
          aria-label={`Decline ${displayName(item.person)}'s request`}>
          Decline
        </button>
      </PersonRow>
      {error && <li role="alert" className="text-sm text-bad">{friendsErrorMessage(error)}</li>}
    </>
  );
}

function Outgoing({ item }: { item: Connection }) {
  const cancel = useRemoveConnection();
  return (
    <PersonRow person={item.person} detail={`Sent ${when(item.created_at)}`}>
      <button type="button" disabled={cancel.isPending} onClick={() => cancel.mutate(item.id)} className={`${small} border border-border hover:bg-surface-2`}
        aria-label={`Cancel your request to ${displayName(item.person)}`}>
        Cancel
      </button>
    </PersonRow>
  );
}

function Section({ title, count, children, empty }: { title: string; count: number; children: ReactNode; empty?: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="space-y-2">
      <h2 id={id} className="text-lg font-semibold">
        {title} <span className="text-sm font-normal text-ink-muted">({count})</span>
      </h2>
      {count === 0 && empty ? <p className="text-sm text-ink-muted">{empty}</p> : <ul className="space-y-2">{children}</ul>}
    </section>
  );
}

export function FriendsPage() {
  const list = useConnections();
  const profile = useProfile();
  const data = list.data;

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 py-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Friends</h1>
        <p className="text-ink-muted">Connect with people you play with. Friends see your bio; nobody sees your serves yet.</p>
      </header>

      {profile.data && !profile.data.username && (
        <div role="status" className="rounded-xl border border-accent/40 bg-accent/10 p-4 text-sm">
          <p className="font-medium">Choose a username to send friend requests</p>
          <p className="mt-1 text-ink-muted">It's how people find you, and how they know who's asking.</p>
          <Link to="/settings#profile" className="mt-2 inline-block font-medium text-accent hover:underline">Choose one in Settings</Link>
        </div>
      )}

      <FindSomeone />

      {list.isError ? (
        <div role="alert" className="space-y-2">
          <p>We couldn't load your friends.</p>
          <button type="button" onClick={() => list.refetch()} className="rounded-lg border border-border px-4 py-2">Try again</button>
        </div>
      ) : !data ? (
        <p className="text-ink-muted">Loading…</p>
      ) : (
        <>
          {data.incoming.length > 0 && (
            <Section title="Requests" count={data.incoming.length}>
              {data.incoming.map((c) => <Incoming key={c.id} item={c} />)}
            </Section>
          )}
          <Section title="Your friends" count={data.friends.length} empty="No friends yet. Find someone by their username above.">
            {data.friends.map((c) => (
              <PersonRow key={c.id} person={c.person} detail={c.accepted_at ? `Friends since ${when(c.accepted_at)}` : undefined} />
            ))}
          </Section>
          {data.outgoing.length > 0 && (
            <Section title="Sent" count={data.outgoing.length}>
              {data.outgoing.map((c) => <Outgoing key={c.id} item={c} />)}
            </Section>
          )}
        </>
      )}
    </div>
  );
}
