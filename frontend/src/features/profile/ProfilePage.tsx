import { useId, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { Link } from "react-router";

import { ApiError } from "../../api/client";
import { useProfile, useRemoveAvatar, useSetAvatar } from "../../api/profile";
import type { Profile } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { AvatarFileError, prepareAvatar } from "../../lib/avatar";
import { bandOf } from "../../lib/score";
import { authErrorMessage } from "../auth/AuthForm";
import { ScoreBar, SCORE_TEXT } from "../results/MetricCards";

function photoError(error: unknown): string {
  if (error instanceof AvatarFileError) return error.message;
  if (error instanceof ApiError && error.status > 0 && error.status < 500) return error.message;
  return authErrorMessage(error);
}

function Photo({ profile }: { profile: Profile }) {
  const input = useRef<HTMLInputElement>(null);
  const setAvatar = useSetAvatar();
  const removeAvatar = useRemoveAvatar();
  const [preparing, setPreparing] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const busy = preparing || setAvatar.isPending || removeAvatar.isPending;
  const name = profile.display_name ?? profile.username;

  async function chosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // choosing the same file again still counts as a change
    if (!file) return;
    setProblem(null);
    setPreparing(true);
    try {
      const jpeg = await prepareAvatar(file);
      await setAvatar.mutateAsync(jpeg);
    } catch (error) {
      setProblem(photoError(error));
    } finally {
      setPreparing(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-2 sm:items-start">
      <Avatar url={profile.avatar_url} name={name} size="lg" />
      <input
        ref={input}
        type="file"
        accept="image/*"
        onChange={chosen}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        data-testid="avatar-input"
      />
      <div className="flex gap-3 text-sm">
        <button type="button" onClick={() => input.current?.click()} disabled={busy} className="font-medium text-accent hover:underline disabled:opacity-50">
          {busy && !removeAvatar.isPending ? "Uploading…" : profile.avatar_url ? "Change photo" : "Add a photo"}
        </button>
        {profile.avatar_url && (
          <button
            type="button"
            onClick={() => {
              setProblem(null);
              removeAvatar.mutate(undefined, { onError: (e) => setProblem(photoError(e)) });
            }}
            disabled={busy}
            className="text-ink-muted hover:text-ink disabled:opacity-50"
          >
            {removeAvatar.isPending ? "Removing…" : "Remove"}
          </button>
        )}
      </div>
      {problem && <p role="alert" className="max-w-56 text-center text-sm text-bad sm:text-left">{problem}</p>}
    </div>
  );
}

function Stat({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="space-y-1.5 rounded-xl border border-border bg-surface p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{label}</p>
      {children}
      {hint && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

function ScoreStat({ score }: { score: number | null | undefined }) {
  if (score == null) return <p className="text-3xl font-semibold text-ink-muted">–</p>;
  const band = bandOf(score);
  return (
    <>
      <p className="flex items-baseline gap-1">
        <span className={`tabular text-3xl font-semibold tracking-tight ${SCORE_TEXT[band]}`}>{score}</span>
        <span className="text-sm text-ink-muted">/ 100</span>
      </p>
      <ScoreBar score={score} label="Score" />
    </>
  );
}

export function ProfilePage() {
  const id = useId();
  const profile = useProfile();
  const p = profile.data;

  if (profile.isError) {
    return (
      <div role="alert" className="space-y-3">
        <p>We couldn't load your profile.</p>
        <button type="button" onClick={() => profile.refetch()} className="rounded-lg border border-border px-4 py-2">Try again</button>
      </div>
    );
  }
  if (!p) return <p className="text-ink-muted">Loading…</p>;

  const { stats } = p;
  const since = new Date(p.member_since).toLocaleDateString(undefined, { month: "long", year: "numeric" });
  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 py-4">
      <section aria-labelledby={`${id}-name`} className="rounded-2xl border border-border bg-surface p-6">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
          <Photo profile={p} />
          <div className="min-w-0 flex-1 space-y-2 text-center sm:text-left">
            <h1 id={`${id}-name`} className="break-words text-2xl font-semibold tracking-tight">
              {p.display_name ?? (p.username ? `@${p.username}` : "Your profile")}
            </h1>
            {p.username ? (
              p.display_name && <p className="text-ink-muted">@{p.username}</p>
            ) : (
              <p className="text-sm">
                <Link to="/settings#profile" className="font-medium text-accent hover:underline">Choose a username</Link>
                <span className="text-ink-muted"> so friends can find you.</span>
              </p>
            )}
            {p.bio ? (
              <p className="whitespace-pre-line break-words">{p.bio}</p>
            ) : (
              <p className="text-sm text-ink-muted">No bio yet.</p>
            )}
            <p className="text-sm text-ink-muted">Member since {since}</p>
            <div className="flex flex-wrap justify-center gap-3 pt-2 sm:justify-start">
              <Link to="/settings#profile" className="rounded-lg border border-border px-4 py-2 text-sm font-semibold hover:bg-surface-2">
                Edit profile
              </Link>
            </div>
          </div>
        </div>
        <p className="mt-6 border-t border-border pt-4 text-xs text-ink-muted">
          {p.username
            ? "People who know your username see your name and picture. Friends also see your bio. Nobody sees your serves."
            : "Nobody can find you until you choose a username."}
        </p>
      </section>

      <section aria-labelledby={`${id}-stats`} className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id={`${id}-stats`} className="text-lg font-semibold">Your serves</h2>
          <Link to="/serves" className="text-sm font-medium text-accent hover:underline">See all</Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Serves analyzed">
            <p className="tabular text-3xl font-semibold tracking-tight">{stats.serves}</p>
          </Stat>
          <Stat
            label="Average score"
            hint={stats.averaged_over ? `Your latest ${stats.averaged_over === 1 ? "serve" : `${stats.averaged_over} scored serves`}.` : "Appears after your first scored serve."}
          >
            <ScoreStat score={stats.average_score} />
          </Stat>
          <Stat label="Best score">
            <ScoreStat score={stats.best_score} />
          </Stat>
        </div>
        <p className="text-xs text-ink-muted">
          Scores compare your angles with reference ranges that haven't been validated yet, so treat them as a guide.
        </p>
      </section>
    </div>
  );
}
