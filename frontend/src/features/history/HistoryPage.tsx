import { useId, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useAnalysesList, useSetNote } from "../../api/queries";
import type { AnalysisSummary } from "../../api/types";
import { DeleteAnalysisButton } from "../../components/DeleteAnalysisButton";
import { StatusIcon, STATUS_TEXT } from "../../components/StatusIcon";
import { beforeAfter, toggleSelection } from "../../lib/compare";
import {
  apiQuery,
  DEFAULT_FILTERS,
  filtersToParams,
  isFiltered,
  KEY_POSITIONS,
  parseFilters,
  type HistoryFilters,
  type KeyPosition,
  type ScoreBand,
} from "../../lib/historyFilters";
import { METRIC_INFO } from "../../lib/metricInfo";
import { bandOf } from "../../lib/score";
import { authErrorMessage } from "../auth/AuthForm";
import { errorCopyFor } from "../processing/errorCopy";
import { ScoreBar, SCORE_TEXT } from "../results/MetricCards";

const MAX_NOTE = 1000;

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

// --- the sidebar -----------------------------------------------------------------------------------

const TIME_OPTIONS: { value: HistoryFilters["time"]; label: string }[] = [
  { value: "all", label: "All time" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "custom", label: "Between dates" },
];
const SCORE_OPTIONS: { value: HistoryFilters["score"]; label: string }[] = [
  { value: "any", label: "Any score" },
  { value: "good", label: "80–100 · good" },
  { value: "borderline", label: "50–79 · borderline" },
  { value: "off", label: "0–49 · needs work" },
];
const BAND_LABELS: Record<ScoreBand, string> = { good: "Good", borderline: "Borderline", off: "Needs work" };

const fieldset = "space-y-1.5";
const legend = "mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted";
const radioRow = "flex cursor-pointer items-center gap-2 text-sm";
const select = "w-full rounded-lg border border-border bg-bg px-2.5 py-1.5 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40";

function FilterSidebar({ filters, onChange }: { filters: HistoryFilters; onChange: (f: HistoryFilters) => void }) {
  const id = useId();
  const set = (patch: Partial<HistoryFilters>) => onChange({ ...filters, ...patch });
  return (
    <div className="space-y-5">
      <fieldset className={fieldset}>
        <legend className={legend}>Uploaded</legend>
        {TIME_OPTIONS.map((o) => (
          <label key={o.value} className={radioRow}>
            <input type="radio" name={`${id}-time`} checked={filters.time === o.value} onChange={() => set({ time: o.value })} className="accent-accent" />
            {o.label}
          </label>
        ))}
        {filters.time === "custom" && (
          <div className="grid grid-cols-2 gap-2 pt-1">
            <label className="space-y-1 text-xs text-ink-muted">
              From
              <input type="date" value={filters.from ?? ""} max={filters.to ?? undefined} onChange={(e) => set({ from: e.target.value || null })} className={select} />
            </label>
            <label className="space-y-1 text-xs text-ink-muted">
              To
              <input type="date" value={filters.to ?? ""} min={filters.from ?? undefined} onChange={(e) => set({ to: e.target.value || null })} className={select} />
            </label>
          </div>
        )}
      </fieldset>

      <fieldset className={fieldset}>
        <legend className={legend}>Serve score</legend>
        {SCORE_OPTIONS.map((o) => (
          <label key={o.value} className={radioRow}>
            <input type="radio" name={`${id}-score`} checked={filters.score === o.value} onChange={() => set({ score: o.value })} className="accent-accent" />
            {o.label}
          </label>
        ))}
      </fieldset>

      <fieldset className={fieldset}>
        <legend className={legend}>Key position</legend>
        <label className="block space-y-1 text-xs text-ink-muted">
          Position
          <select
            value={filters.stat ?? ""}
            onChange={(e) => {
              const stat = (e.target.value || null) as KeyPosition | null;
              set({ stat, band: stat ? (filters.band ?? "off") : null });
            }}
            className={select}
          >
            <option value="">Any position</option>
            {KEY_POSITIONS.map((m) => (
              <option key={m} value={m}>{METRIC_INFO[m].title}</option>
            ))}
          </select>
        </label>
        {filters.stat && (
          <label className="block space-y-1 text-xs text-ink-muted">
            Rated
            <select value={filters.band ?? "off"} onChange={(e) => set({ band: e.target.value as ScoreBand })} className={select}>
              {(Object.keys(BAND_LABELS) as ScoreBand[]).map((b) => (
                <option key={b} value={b}>{BAND_LABELS[b]}</option>
              ))}
            </select>
          </label>
        )}
      </fieldset>

      {isFiltered(filters) && (
        <button type="button" onClick={() => onChange(DEFAULT_FILTERS)} className="text-sm font-medium text-accent hover:underline">
          Clear filters
        </button>
      )}
    </div>
  );
}

// --- one serve -----------------------------------------------------------------------------------

function Thumbnail({ analysis }: { analysis: AnalysisSummary }) {
  if (analysis.thumbnail_url) {
    return <img src={analysis.thumbnail_url} alt="" loading="lazy" className="aspect-video h-full w-full bg-black object-contain" />;
  }
  return (
    <div className="grid aspect-video h-full w-full place-items-center bg-surface-2 text-ink-muted" aria-hidden>
      <svg viewBox="0 0 24 24" className="size-8" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m10 9 5 3-5 3z" fill="currentColor" />
      </svg>
    </div>
  );
}

function StatusLine({ analysis }: { analysis: AnalysisSummary }) {
  if (analysis.status === "succeeded") return analysis.counts ? <CountsSummary counts={analysis.counts} /> : null;
  if (analysis.status === "failed") return <p className="text-sm text-bad">Failed · {errorCopyFor(analysis.error?.code).title}</p>;
  if (analysis.status === "awaiting_upload") return <p className="text-sm text-ink-muted">Upload not finished</p>;
  return <p className="text-sm text-accent">Processing…</p>;
}

function ScoreBlock({ analysis }: { analysis: AnalysisSummary }) {
  const score = analysis.overall_score ?? null;
  if (analysis.status !== "succeeded") return null;
  if (score === null) return <p className="text-sm text-ink-muted">No score</p>;
  const band = bandOf(score);
  return (
    <div className="w-full space-y-1.5 sm:w-44">
      <div className="flex items-baseline justify-between gap-2">
        <p className="flex items-baseline gap-1">
          <span className={`tabular text-3xl font-semibold tracking-tight ${SCORE_TEXT[band]}`} data-testid="history-score">{score}</span>
          <span className="text-sm text-ink-muted">/ 100</span>
        </p>
        <span className="inline-flex items-center gap-1 text-xs font-medium">
          <StatusIcon status={band} className="size-3" />
          {STATUS_TEXT[band]}
        </span>
      </div>
      <ScoreBar score={score} label="Serve score" />
    </div>
  );
}

/** The key positions' scores: the card's "sub analytics". */
function Details({ analysis }: { analysis: AnalysisSummary }) {
  const scores = analysis.key_scores as Record<KeyPosition, { score: number; band: ScoreBand } | null> | null | undefined;
  return (
    <div className="space-y-3 border-t border-border p-4">
      <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
        {KEY_POSITIONS.map((m) => {
          const s = scores?.[m] ?? null;
          return (
            <li key={m} className="space-y-1">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span>{METRIC_INFO[m].title}</span>
                {s ? (
                  <span className={`tabular font-semibold ${SCORE_TEXT[s.band]}`}>{s.score}</span>
                ) : (
                  <span className="text-xs text-ink-muted">Not measured</span>
                )}
              </div>
              {s && <ScoreBar score={s.score} label={`${METRIC_INFO[m].title} score`} />}
            </li>
          );
        })}
      </ul>
      <Link to={`/analyses/${analysis.id}`} className="inline-block text-sm font-medium text-accent hover:underline">
        Open the full analysis
      </Link>
    </div>
  );
}

function Note({ analysis }: { analysis: AnalysisSummary }) {
  const id = useId();
  const save = useSetNote(analysis.id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  function start() {
    setDraft(analysis.note ?? "");
    save.reset();
    setEditing(true);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(draft, { onSuccess: () => setEditing(false) });
  }

  if (editing) {
    return (
      <form onSubmit={submit} className="space-y-2" aria-label="Note">
        <label htmlFor={`${id}-note`} className="sr-only">Note on {analysis.filename}</label>
        <textarea
          id={`${id}-note`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={MAX_NOTE}
          rows={2}
          autoFocus
          placeholder="Anything you want to remember: what you worked on, how it felt, the conditions…"
          className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        {save.error && <p role="alert" className="text-sm text-bad">{authErrorMessage(save.error)}</p>}
        <div className="flex items-center gap-2">
          <button type="submit" disabled={save.isPending} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent hover:bg-accent-strong disabled:opacity-50">
            {save.isPending ? "Saving…" : "Save note"}
          </button>
          <button type="button" onClick={() => setEditing(false)} className="rounded-lg px-3 py-1.5 text-sm text-ink-muted hover:text-ink">
            Cancel
          </button>
          <span className="ml-auto text-xs text-ink-muted tabular">{draft.length}/{MAX_NOTE}</span>
        </div>
      </form>
    );
  }
  if (analysis.note) {
    return (
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 whitespace-pre-line break-words border-l-2 border-border pl-2.5 text-sm text-ink" data-testid="history-note">
          {analysis.note}
        </p>
        <button type="button" onClick={start} className="shrink-0 text-sm text-accent hover:underline" aria-label={`Edit the note on ${analysis.filename}`}>
          Edit
        </button>
      </div>
    );
  }
  return (
    <button type="button" onClick={start} className="text-sm text-ink-muted hover:text-ink" aria-label={`Add a note to ${analysis.filename}`}>
      + Add a note
    </button>
  );
}

function AnalysisCard({ analysis, selected, onToggle, onDeleted }: {
  analysis: AnalysisSummary;
  selected: boolean;
  onToggle: () => void;
  onDeleted: () => void;
}) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const succeeded = analysis.status === "succeeded";
  return (
    <article
      aria-labelledby={`${detailsId}-title`}
      className={`overflow-hidden rounded-xl border bg-surface ${selected ? "border-accent ring-2 ring-accent/40" : "border-border"}`}
      data-testid={`history-${analysis.id}`}
    >
      <div className="flex flex-col gap-4 p-3 sm:flex-row sm:items-center">
        <Link to={`/analyses/${analysis.id}`} className="block w-full shrink-0 overflow-hidden rounded-lg sm:w-44" tabIndex={-1} aria-hidden>
          <Thumbnail analysis={analysis} />
        </Link>
        <div className="min-w-0 flex-1 space-y-1.5">
          <h2 id={`${detailsId}-title`} className="truncate font-medium" title={analysis.filename}>
            <Link to={`/analyses/${analysis.id}`} className="hover:underline">{analysis.filename}</Link>
          </h2>
          <p className="text-sm text-ink-muted">
            <time dateTime={analysis.created_at}>{formatWhen(analysis.created_at)}</time> ·{" "}
            {analysis.hand === "right" ? "Right" : "Left"}-handed
          </p>
          <StatusLine analysis={analysis} />
          <Note analysis={analysis} />
        </div>
        <ScoreBlock analysis={analysis} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border px-3 py-2">
        {succeeded && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls={`${detailsId}-details`}
            className="text-sm font-medium text-accent hover:underline"
          >
            {open ? "Hide details" : "Show details"}
          </button>
        )}
        {succeeded && (
          <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-muted hover:text-ink">
            <input type="checkbox" checked={selected} onChange={onToggle} className="size-4 accent-[var(--accent)]" />
            Select to compare
          </label>
        )}
        <DeleteAnalysisButton id={analysis.id} filename={analysis.filename} onDeleted={onDeleted} className="ml-auto" />
      </div>
      {open && (
        <div id={`${detailsId}-details`}>
          <Details analysis={analysis} />
        </div>
      )}
    </article>
  );
}

// --- the page ------------------------------------------------------------------------------------

export function HistoryPage() {
  const [params, setParams] = useSearchParams();
  // The URL holds the filters, but the router updates it a moment later, so the controls would
  // flick back to the old value first. Keep them in state too, and follow the URL when it moves
  // on its own (Back, a link).
  const search = params.toString();
  const [filters, setFilters] = useState(() => parseFilters(params));
  const [seenSearch, setSeenSearch] = useState(search);
  if (search !== seenSearch) {
    setSeenSearch(search);
    setFilters(parseFilters(params));
  }
  const query = useMemo(() => apiQuery(filters), [filters]);
  const list = useAnalysesList(query);
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersId = useId();
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const filtered = isFiltered(filters);

  function changeFilters(next: HistoryFilters) {
    setFilters(next);
    setParams(filtersToParams(next), { replace: true, preventScrollReset: true });
  }

  function compare() {
    const picked = selected.map((id) => items.find((a) => a.id === id)).filter((a): a is AnalysisSummary => !!a);
    if (picked.length !== 2) return;
    const [before, after] = beforeAfter(picked[0]!, picked[1]!);
    navigate(`/compare?a=${before.id}&b=${after.id}`);
  }

  return (
    <div className="space-y-6 pb-20">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">History</h1>
          <p className="text-ink-muted">Every serve you've analyzed. Pick two to compare them side by side, aligned by phase.</p>
        </div>
        <Link to="/" className="rounded-lg bg-accent px-4 py-2 font-semibold text-on-accent hover:bg-accent-strong">
          Analyze a new serve
        </Link>
      </header>

      <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside aria-label="Filters" className="rounded-xl border border-border bg-surface p-4 lg:sticky lg:top-20 lg:self-start">
          {/* On phones the filters fold away above the list; on wide screens they're always open. */}
          <button
            type="button"
            onClick={() => setFiltersOpen((v) => !v)}
            aria-expanded={filtersOpen}
            aria-controls={filtersId}
            className="flex w-full items-center justify-between text-sm font-semibold lg:hidden"
          >
            Filters{filtered ? " (on)" : ""}
            <span aria-hidden>{filtersOpen ? "−" : "+"}</span>
          </button>
          <div id={filtersId} className={`${filtersOpen ? "mt-4 block" : "hidden"} lg:mt-0 lg:block`}>
            <FilterSidebar filters={filters} onChange={changeFilters} />
          </div>
        </aside>

        <section aria-label="Your serves" className="min-w-0 space-y-4">
          {list.isError && !list.data ? (
            <div role="alert" className="space-y-3">
              <p>We couldn't load your history.</p>
              <button type="button" onClick={() => list.refetch()} className="rounded-lg border border-border px-4 py-2">
                Try again
              </button>
            </div>
          ) : list.isPending ? (
            <p className="text-ink-muted">Loading…</p>
          ) : items.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-10 text-center">
              {filtered ? (
                <>
                  <p className="font-medium">No serves match these filters</p>
                  <button type="button" onClick={() => changeFilters(DEFAULT_FILTERS)} className="mt-2 text-sm font-medium text-accent hover:underline">
                    Clear filters
                  </button>
                </>
              ) : (
                <>
                  <p className="font-medium">No analyses yet</p>
                  <p className="text-ink-muted">Upload your first serve to get started.</p>
                </>
              )}
            </div>
          ) : (
            <ul className="space-y-3">
              {items.map((a) => (
                <li key={a.id}>
                  <AnalysisCard
                    analysis={a}
                    selected={selected.includes(a.id)}
                    onToggle={() => setSelected((s) => toggleSelection(s, a.id))}
                    onDeleted={() => setSelected((s) => s.filter((id) => id !== a.id))}
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
        </section>
      </div>

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
