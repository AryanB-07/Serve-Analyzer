import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { useFollow, useFollows, useLeaderboard, useRemoveFollower, useUnfollow } from "../../api/friends";
import { useProfile } from "../../api/profile";
import type { FollowEntry, FollowLists, LeaderboardEntry, PersonSummary } from "../../api/types";
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

type Tab = "friends" | "followers" | "following";
const TABS: { key: Tab; label: string; empty: string }[] = [
  { key: "friends", label: "Friends", empty: "No friends yet. Friends are people you follow who follow you back." },
  { key: "followers", label: "Followers", empty: "Nobody follows you yet." },
  { key: "following", label: "Following", empty: "You don't follow anyone yet. Find someone by their username above." },
];

/** One person in a list, with what you can do about them from here. */
function FollowRow({ entry, tab }: { entry: FollowEntry; tab: Tab }) {
  const follow = useFollow();
  const unfollow = useUnfollow();
  const remove = useRemoveFollower();
  const [confirming, setConfirming] = useState<null | "unfollow" | "remove">(null);
  const name = displayName(entry.person);
  const username = entry.person.username;
  const busy = follow.isPending || unfollow.isPending || remove.isPending;
  const error = follow.error ?? unfollow.error ?? remove.error;
  const detail = tab === "friends" ? `Friends since ${when(entry.since)}`
    : tab === "followers" ? `Followed you ${when(entry.since)}${entry.you_follow ? " · you follow back" : ""}`
      : `Following since ${when(entry.since)}${entry.follows_you ? " · follows you" : ""}`;
  if (!username) return <PersonRow person={entry.person} detail={detail} />;
  const done = { onSuccess: () => setConfirming(null) };
  return (
    <>
      <PersonRow person={entry.person} detail={detail}>
        {confirming ? (
          <>
            <span className="self-center text-xs text-ink-muted">
              {confirming === "remove" ? `Remove ${name} from your followers? They won't be told.`
                : tab === "friends" ? `Unfollow ${name}? You won't be friends any more.` : `Unfollow ${name}?`}
            </span>
            <button type="button" disabled={busy}
              onClick={() => (confirming === "remove" ? remove.mutate(username, done) : unfollow.mutate(username, done))}
              className={`${small} border border-border hover:bg-surface-2`}>
              {confirming === "remove" ? "Remove" : "Unfollow"}
            </button>
            <button type="button" onClick={() => setConfirming(null)} className="px-2 text-sm text-ink-muted hover:text-ink">Cancel</button>
          </>
        ) : (
          <>
            {tab === "followers" && !entry.you_follow && (
              <button type="button" disabled={busy} onClick={() => follow.mutate(username)}
                className={`${small} bg-accent text-on-accent hover:bg-accent-strong`} aria-label={`Follow ${name} back`}>
                Follow back
              </button>
            )}
            {tab === "followers" ? (
              <button type="button" onClick={() => setConfirming("remove")} className={`${small} border border-border hover:bg-surface-2`}
                aria-label={`Remove ${name} from your followers`}>
                Remove
              </button>
            ) : (
              <button type="button" onClick={() => setConfirming("unfollow")} className={`${small} border border-border hover:bg-surface-2`}
                aria-label={tab === "friends" ? `Unfriend ${name}` : `Unfollow ${name}`}>
                {tab === "friends" ? "Unfriend" : "Unfollow"}
              </button>
            )}
          </>
        )}
      </PersonRow>
      {error && <li role="alert" className="text-sm text-bad">{friendsErrorMessage(error)}</li>}
    </>
  );
}

function FollowTabs({ lists }: { lists: FollowLists }) {
  const [tab, setTab] = useState<Tab>(lists.counts.friends > 0 || lists.counts.followers === 0 ? "friends" : "followers");
  const id = useId();
  const current = TABS.find((t) => t.key === tab)!;
  const items = lists[tab];
  return (
    <section aria-label="Your friends, followers and following" className="space-y-3">
      <div role="tablist" aria-label="Lists" className="flex gap-1 rounded-xl border border-border bg-surface p-1">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" id={`${id}-${t.key}`} aria-selected={tab === t.key} aria-controls={`${id}-panel`}
            onClick={() => setTab(t.key)}
            className={`flex-1 rounded-lg px-2 py-1.5 text-sm font-medium ${tab === t.key ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink"}`}>
            {t.label} <span className="tabular text-ink-muted">{lists.counts[t.key]}</span>
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${tab}`}>
        {items.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">{current.empty}</p>
        ) : (
          <ul className="space-y-2">
            {items.map((e) => <FollowRow key={`${tab}-${e.person.username}`} entry={e} tab={tab} />)}
          </ul>
        )}
      </div>
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
  const follows = useFollows();
  const profile = useProfile();
  const data = follows.data;

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 py-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Friends</h1>
        <p className="text-ink-muted">
          Follow people you play with. When they follow you back you're friends: you see each other's bio, can message,
          and see whatever serve stats each of you shares.
        </p>
      </header>

      {profile.data && !profile.data.username && (
        <div role="status" className="rounded-xl border border-accent/40 bg-accent/10 p-4 text-sm">
          <p className="font-medium">Choose a username to follow people</p>
          <p className="mt-1 text-ink-muted">It's how people find you, and how they see who's following them.</p>
          <Link to="/settings#profile" className="mt-2 inline-block font-medium text-accent hover:underline">Choose one in Settings</Link>
        </div>
      )}

      <FindSomeone />

      {follows.isError ? (
        <div role="alert" className="space-y-2">
          <p>We couldn't load your friends.</p>
          <button type="button" onClick={() => follows.refetch()} className="rounded-lg border border-border px-4 py-2">Try again</button>
        </div>
      ) : !data ? (
        <p className="text-ink-muted">Loading…</p>
      ) : (
        <>
          <FollowTabs lists={data} />
          {data.counts.friends > 0 && <LeaderboardSection />}
        </>
      )}
    </div>
  );
}
