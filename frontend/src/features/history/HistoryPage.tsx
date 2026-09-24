import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { useAnalysesList } from "../../api/queries";
import type { AnalysisSummary } from "../../api/types";
import { StatusIcon } from "../../components/StatusIcon";
import { beforeAfter, toggleSelection } from "../../lib/compare";
import { errorCopyFor } from "../processing/errorCopy";

function formatWhen(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** "3 good, 2 borderline, 0 needs work" with shapes; unknown counts are left out. */
export function CountsSummary({ counts }: { counts: NonNullable<AnalysisSummary["counts"]> }) {
  const items = [
    { status: "good" as const, n: counts.good, word: "good" },
    { status: "borderline" as const, n: counts.borderline, word: "borderline" },
    { status: "off" as const, n: counts.off, word: "need work" },
  ];
  return (
    <p className="flex flex-wrap items-center gap-x-3 text-sm">
      <span className="sr-only">{items.map((i) => `${i.n} ${i.word}`).join(", ")}</span>
      {items.map((i) => (
        <span key={i.status} className="inline-flex items-center gap-1" aria-hidden>
          <StatusIcon status={i.status} className="size-3" />
          <span className="tabular font-medium">{i.n}</span>
          <span className="text-ink-muted">{i.word}</span>
        </span>
      ))}
    </p>
  );
}

function StatusLine({ analysis }: { analysis: AnalysisSummary }) {
  if (analysis.status === "succeeded" && analysis.counts) return <CountsSummary counts={analysis.counts} />;
  if (analysis.status === "failed") {
    return <p className="text-sm text-bad">Failed · {errorCopyFor(analysis.error?.code).title}</p>;
  }
  if (analysis.status === "awaiting_upload") return <p className="text-sm text-ink-muted">Upload not finished</p>;
  return <p className="text-sm text-accent">Processing…</p>;
}

function Thumbnail({ analysis }: { analysis: AnalysisSummary }) {
  if (analysis.thumbnail_url) {
    return <img src={analysis.thumbnail_url} alt="" loading="lazy" className="aspect-video w-full bg-black object-contain" />;
  }
  return (
    <div className="grid aspect-video w-full place-items-center bg-surface-2 text-ink-muted" aria-hidden>
      <svg viewBox="0 0 24 24" className="size-8" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m10 9 5 3-5 3z" fill="currentColor" />
      </svg>
    </div>
  );
}

function AnalysisCard({
  analysis,
  selected,
  onToggle,
}: {
  analysis: AnalysisSummary;
  selected: boolean;
  onToggle: () => void;
}) {
  const comparable = analysis.status === "succeeded";
  return (
    <article
      className={`overflow-hidden rounded-xl border bg-surface ${selected ? "border-accent ring-2 ring-accent/40" : "border-border"}`}
      data-testid={`history-${analysis.id}`}
    >
      <Link to={`/analyses/${analysis.id}`} className="group block">
        <Thumbnail analysis={analysis} />
        <div className="space-y-1 p-3 pb-2">
          <h2 className="truncate font-medium group-hover:underline" title={analysis.filename}>{analysis.filename}</h2>
          <p className="text-sm text-ink-muted">
            {formatWhen(analysis.created_at)} · {analysis.hand === "right" ? "Right" : "Left"}-handed
          </p>
          <StatusLine analysis={analysis} />
        </div>
      </Link>
      {comparable && (
        <label className="flex cursor-pointer items-center gap-2 border-t border-border px-3 py-2 text-sm text-ink-muted hover:text-ink">
          <input type="checkbox" checked={selected} onChange={onToggle} className="size-4 accent-[var(--accent)]" />
          Select to compare
        </label>
      )}
    </article>
  );
}

export function HistoryPage() {
  const list = useAnalysesList();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string[]>([]);
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];

  function compare() {
    const picked = selected.map((id) => items.find((a) => a.id === id)).filter((a): a is AnalysisSummary => !!a);
    if (picked.length !== 2) return;
    const [before, after] = beforeAfter(picked[0]!, picked[1]!);
    navigate(`/compare?a=${before.id}&b=${after.id}`);
  }

  if (list.isError && !list.data) {
    return (
      <div role="alert" className="space-y-3">
        <p>We couldn't load your history.</p>
        <button type="button" onClick={() => list.refetch()} className="rounded-lg border border-border px-4 py-2">
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-20">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">History</h1>
          <p className="text-ink-muted">Pick two serves to compare them side by side, aligned by phase.</p>
        </div>
        <Link to="/" className="rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent hover:bg-accent-strong">
          Analyze a new serve
        </Link>
      </header>

      {list.isPending ? (
        <p className="text-ink-muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center">
          <p className="font-medium">No analyses yet</p>
          <p className="text-ink-muted">Upload your first serve to get started.</p>
        </div>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((a) => (
            <li key={a.id}>
              <AnalysisCard
                analysis={a}
                selected={selected.includes(a.id)}
                onToggle={() => setSelected((s) => toggleSelection(s, a.id))}
              />
            </li>
          ))}
        </ul>
      )}

      {list.hasNextPage && (
        <div className="text-center">
          <button
            type="button"
            onClick={() => list.fetchNextPage()}
            disabled={list.isFetchingNextPage}
            className="rounded-lg border border-border px-4 py-2 font-medium hover:bg-surface-2 disabled:opacity-50"
          >
            {list.isFetchingNextPage ? "Loading…" : "Load more"}
          </button>
        </div>
      )}

      {selected.length > 0 && (
        <div className="sticky bottom-4 z-30 mx-auto flex max-w-lg items-center justify-between gap-3 rounded-xl border border-border bg-surface p-3 shadow-xl" role="region" aria-label="Compare selection">
          <p className="text-sm" aria-live="polite">
            {selected.length === 1 ? "Select one more serve to compare." : "2 serves selected."}
          </p>
          <div className="flex gap-2">
            <button type="button" onClick={() => setSelected([])} className="rounded-lg px-3 py-1.5 text-sm text-ink-muted hover:text-ink">
              Clear
            </button>
            <button
              type="button"
              onClick={compare}
              disabled={selected.length !== 2}
              className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50"
            >
              Compare
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
