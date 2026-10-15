import { useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError } from "../../api/client";
import { useBlock, useFollow, usePerson, useRemoveFollower, useUnfollow } from "../../api/friends";
import { useStartConversation } from "../../api/messages";
import type { Person } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Sparkline } from "../../components/Sparkline";
import { KEY_POSITIONS } from "../../lib/historyFilters";
import { METRIC_INFO } from "../../lib/metricInfo";
import { bandOf } from "../../lib/score";
import { ScoreBar, SCORE_TEXT } from "../results/MetricCards";
import { ReportForm } from "../messages/ReportForm";
import { displayName, FollowTabs, friendsErrorMessage } from "./FriendsPage";

const primary = "rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50";
const secondary = "rounded-lg border border-border px-4 py-2 text-sm font-semibold hover:bg-surface-2 disabled:opacity-50";
const when = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });

function Actions({ person }: { person: Person }) {
  const follow = useFollow();
  const unfollow = useUnfollow();
  const removeFollower = useRemoveFollower();
  const start = useStartConversation();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState<null | "unfollow" | "remove">(null);
  const busy = follow.isPending || unfollow.isPending || removeFollower.isPending;
  const error = follow.error ?? unfollow.error ?? removeFollower.error ?? start.error;
  const name = displayName(person);
  const username = person.username!;
  const done = { onSuccess: () => setConfirming(null) };
  const message = () => start.mutate(username, { onSuccess: (c) => navigate(`/messages/${c.id}`) });

  let actions;
  if (confirming) {
    actions = (
      <>
        <p className="w-full text-sm">
          {confirming === "remove" ? `Remove ${name} from your followers? They won't be told.`
            : person.relationship === "friends" ? `Unfollow ${name}? You won't be friends any more, and they won't be told.`
              : `Unfollow ${name}?`}
        </p>
        <button type="button" disabled={busy} className={secondary}
          onClick={() => (confirming === "remove" ? removeFollower.mutate(username, done) : unfollow.mutate(username, done))}>
          {confirming === "remove" ? "Remove follower" : "Unfollow"}
        </button>
        <button type="button" onClick={() => setConfirming(null)} className="px-2 text-sm text-ink-muted hover:text-ink">Cancel</button>
      </>
    );
  } else {
    switch (person.relationship) {
      case "self":
        actions = <Link to="/profile" className={secondary}>This is you: open your profile</Link>;
        break;
      case "none":
        actions = person.can_follow ? (
          <button type="button" disabled={busy} onClick={() => follow.mutate(username)} className={primary}>
            {follow.isPending ? "Following…" : "Follow"}
          </button>
        ) : (
          <p className="text-sm text-ink-muted">{name} isn't accepting new followers.</p>
        );
        break;
      case "follows_you":
        actions = (
          <>
            <p className="w-full text-sm">{name} follows you. Follow back to be friends.</p>
            <button type="button" disabled={busy} onClick={() => follow.mutate(username)} className={primary}>Follow back</button>
            <button type="button" onClick={() => setConfirming("remove")} className="text-sm text-ink-muted hover:text-ink">Remove follower…</button>
          </>
        );
        break;
      case "following":
        actions = (
          <>
            <p className="text-sm text-ink-muted">You follow {name}. You'll be friends if they follow you back.</p>
            <button type="button" onClick={() => setConfirming("unfollow")} className={secondary}>Unfollow</button>
          </>
        );
        break;
      case "friends":
        actions = (
          <>
            <button type="button" disabled={start.isPending} onClick={message} className={primary}>
              {start.isPending ? "Opening…" : "Message"}
            </button>
            <p className="text-sm text-good">Friends{person.friends_since ? ` since ${when(person.friends_since)}` : ""}</p>
            <button type="button" onClick={() => setConfirming("unfollow")} className="text-sm text-ink-muted hover:text-ink">Unfriend…</button>
          </>
        );
        break;
    }
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-center gap-3 sm:justify-start">{actions}</div>
      {error && <p role="alert" className="text-sm text-bad">{friendsErrorMessage(error)}</p>}
    </div>
  );
}

function Counts({ person }: { person: Person }) {
  const { followers, following, friends } = person.counts;
  const item = (n: number, one: string, many: string) => (
    <span><span className="tabular font-semibold text-ink">{n}</span> {n === 1 ? one : many}</span>
  );
  return (
    <p className="flex flex-wrap justify-center gap-x-4 text-sm text-ink-muted sm:justify-start">
      {item(followers, "follower", "followers")}
      {item(following, "following", "following")}
      {item(friends, "friend", "friends")}
    </p>
  );
}

function StatCard({ label, score, hint }: { label: string; score: number | null | undefined; hint?: string }) {
  return (
    <div className="space-y-1.5 rounded-xl border border-border bg-surface p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{label}</p>
      {score == null ? (
        <p className="text-3xl font-semibold text-ink-muted">–</p>
      ) : (
        <>
          <p className="flex items-baseline gap-1">
            <span className={`tabular text-3xl font-semibold tracking-tight ${SCORE_TEXT[bandOf(score)]}`}>{score}</span>
            <span className="text-sm text-ink-muted">/ 100</span>
          </p>
          <ScoreBar score={score} label={label} />
        </>
      )}
      {hint && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

/** What a friend chose to share of their serves. */
function FriendServes({ person }: { person: Person }) {
  const id = useId();
  const { stats, positions } = person;
  const name = displayName(person);
  if (person.relationship !== "friends") return null;
  if (!stats && !positions) {
    return <p className="text-sm text-ink-muted">{name} isn't sharing serve stats with friends.</p>;
  }
  const trend = stats?.trend.map((t) => t.score) ?? [];
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h2 id={id} className="text-lg font-semibold">{name}'s serves</h2>
      {stats && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5 rounded-xl border border-border bg-surface p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Serves analyzed</p>
              <p className="tabular text-3xl font-semibold tracking-tight">{stats.serves}</p>
            </div>
            <StatCard
              label="Average score"
              score={stats.average_score}
              hint={stats.averaged_over ? `Their latest ${stats.averaged_over === 1 ? "serve" : `${stats.averaged_over} scored serves`}.` : "No scored serves yet."}
            />
            <StatCard label="Best score" score={stats.best_score} />
          </div>
          {trend.length >= 2 && (
            <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Trend</p>
                <Sparkline scores={trend} label={`Scores of ${name}'s latest ${trend.length} serves, from ${trend[0]} to ${trend[trend.length - 1]}`} />
              </div>
              {stats.change != null && (
                <p className="text-sm">
                  <span className={`tabular font-semibold ${stats.change > 0 ? "text-good" : stats.change < 0 ? "text-bad" : ""}`}>
                    {stats.change > 0 ? "+" : ""}{stats.change}
                  </span>{" "}
                  <span className="text-ink-muted">over their latest 5 serves</span>
                </p>
              )}
            </div>
          )}
        </>
      )}
      {positions && (
        <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Key positions</p>
          <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
            {KEY_POSITIONS.map((m) => {
              const p = positions[m];
              return (
                <li key={m} className="space-y-1">
                  <div className="flex items-baseline justify-between gap-2 text-sm">
                    <span>{METRIC_INFO[m].title}</span>
                    {p ? <span className={`tabular font-semibold ${SCORE_TEXT[bandOf(p.score)]}`}>{p.score}</span> : <span className="text-xs text-ink-muted">Not measured</span>}
                  </div>
                  {p && <ScoreBar score={p.score} label={`${METRIC_INFO[m].title} average`} />}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <p className="text-xs text-ink-muted">
        Scores compare angles with reference ranges that haven't been validated yet, so treat them as a guide.
      </p>
    </section>
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
        Block {name}? Neither of you will follow the other any more. They won't be able to find you, and won't be told.
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
  const [reporting, setReporting] = useState(false);

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
            <Counts person={p} />
            {p.bio && <p className="whitespace-pre-line break-words">{p.bio}</p>}
            {p.relationship !== "friends" && p.relationship !== "self" && (
              <p className="text-xs text-ink-muted">Friends (people who follow each other) see more of each other's profile.</p>
            )}
            <Actions person={p} />
          </div>
        </div>
      </section>
      <FriendServes person={p} />
      {p.can_see_lists && p.relationship === "friends" && p.username && (
        <FollowTabs username={p.username} counts={p.counts} own={false} name={displayName(p)} />
      )}
      {p.relationship !== "self" && (
        <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
          <BlockControl person={p} onBlocked={setBlocked} />
          {reporting ? (
            <div className="w-full">
              <ReportForm username={p.username!} name={displayName(p)} onDone={() => setReporting(false)} onBlocked={() => setBlocked(displayName(p))} />
            </div>
          ) : (
            <button type="button" onClick={() => setReporting(true)} className="text-sm text-ink-muted hover:text-bad">Report {displayName(p)}…</button>
          )}
        </div>
      )}
    </div>
  );
}
