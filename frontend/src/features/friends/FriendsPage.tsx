import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { useAcceptRequest, useConnections, useLeaderboard, useRemoveConnection } from "../../api/friends";
import { useProfile } from "../../api/profile";
import type { Connection, LeaderboardEntry, PersonSummary } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { bandOf } from "../../lib/score";
import { normaliseUsername, usernameProblem } from "../../lib/username";
import { authErrorMessage } from "../auth/AuthForm";
import { SCORE_TEXT } from "../results/MetricCards";

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

function LeaderboardRow({ entry }: { entry: LeaderboardEntry }) {
  const name = entry.is_you ? `${displayName(entry.person)} (you)` : displayName(entry.person);
  const score = entry.average_score;
  return (
    <li
      className={`flex items-center gap-3 rounded-xl border p-3 ${entry.is_you ? "border-accent bg-accent/10" : "border-border bg-surface"}`}
      aria-current={entry.is_you ? "true" : undefined}
    >
      <span className="tabular w-7 shrink-0 text-center text-lg font-semibold text-ink-muted" aria-label={entry.rank ? `Rank ${entry.rank}` : "Not ranked"}>
        {entry.rank ?? "–"}
      </span>
      <Avatar url={entry.person.avatar_url} name={entry.person.display_name ?? entry.person.username} size="sm" />
      <div className="min-w-0 flex-1">
        {entry.person.username && !entry.is_you ? (
          <Link to={`/u/${entry.person.username}`} className="block truncate font-medium hover:underline">{name}</Link>
        ) : (
          <p className="truncate font-medium">{name}</p>
        )}
        <p className="text-xs text-ink-muted">
          {entry.needed
            ? `${entry.needed} more ${entry.needed === 1 ? "serve" : "serves"} to be ranked`
            : `${entry.scored_serves} scored ${entry.scored_serves === 1 ? "serve" : "serves"}`}
        </p>
      </div>
      {score != null && (
        <span className={`tabular shrink-0 text-xl font-semibold ${SCORE_TEXT[bandOf(score)]}`}>{score}</span>
      )}
    </li>
  );
}

function LeaderboardSection() {
  const id = useId();
  const board = useLeaderboard();
  const data = board.data;
  if (!data) return null;
  const empty = data.ranked.length === 0 && data.not_ranked.length === 0;
  return (
    <section aria-labelledby={id} className="space-y-2">
      <h2 id={id} className="text-lg font-semibold">Leaderboard</h2>
      <p className="text-sm text-ink-muted">
        The average of each person's latest {data.averaged_over} scored serves from the last {data.window_days} days.
        You need {data.min_serves} serves in that time to be ranked.
      </p>
      {empty ? (
        <p className="text-sm text-ink-muted">Nobody's on it yet. People join from Settings.</p>
      ) : (
        <ol className="space-y-2">
          {[...data.ranked, ...data.not_ranked].map((e) => (
            <LeaderboardRow key={`${e.person.username}-${e.is_you}`} entry={e} />
          ))}
        </ol>
      )}
      {!data.you_are_on_it && (
        <p className="text-sm">
          <span className="text-ink-muted">You're not on it. </span>
          <Link to="/settings#sharing" className="font-medium text-accent hover:underline">Join from Settings</Link>
        </p>
      )}
      <p className="text-xs text-ink-muted">Scores use reference ranges that haven't been validated yet, so treat ranks as a guide.</p>
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
        <p className="text-ink-muted">Connect with people you play with. Friends see your bio, and whatever you choose to share in Settings.</p>
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
          {data.friends.length > 0 && <LeaderboardSection />}
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
