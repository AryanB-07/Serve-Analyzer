import { Link } from "react-router";

import { useAnalyses } from "../../api/queries";

/** Milestone 2 placeholder list. Thumbnails, summaries and compare arrive in milestone 8. */
export function HistoryPage() {
  const { data, isError, error } = useAnalyses();
  if (isError) return <p role="alert">Could not load history: {error.message}</p>;
  if (!data) return <p>Loading…</p>;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">History</h1>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data.items.map((a) => (
          <li key={a.id}>
            <Link
              to={`/analyses/${a.id}`}
              className="block overflow-hidden rounded-xl border border-border bg-surface hover:border-accent"
            >
              {a.thumbnail_url && <img src={a.thumbnail_url} alt="" className="aspect-video w-full object-cover" />}
              <div className="p-3">
                <p className="font-medium">{a.filename}</p>
                <p className="text-sm text-ink-muted">{new Date(a.created_at).toLocaleDateString()} · {a.status}</p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
