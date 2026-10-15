import { useId, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../../api/client";
import { useAcceptRequest, useBlock, usePerson, useRemoveConnection, useSendRequest } from "../../api/friends";
import type { Person } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Sparkline } from "../../components/Sparkline";
import { KEY_POSITIONS } from "../../lib/historyFilters";
import { METRIC_INFO } from "../../lib/metricInfo";
import { bandOf } from "../../lib/score";
import { ScoreBar, SCORE_TEXT } from "../results/MetricCards";
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
      <FriendServes person={p} />
      {p.relationship !== "self" && <BlockControl person={p} onBlocked={setBlocked} />}
    </div>
  );
}
