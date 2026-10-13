/** What the analysis can't do, in plain words (the README's "Known limitations", for players). */
export const LIMITS: [title: string, detail: string][] = [
  [
    "It measures the flat picture",
    "Angles come from one camera's 2D view, so they're accurate only when it's side-on and level. Turning toward or away from the camera, like the shoulder turn, isn't measured.",
  ],
  [
    "It doesn't see the ball or racket",
    "Contact is the moment your hitting wrist is highest. A swing that misses the ball looks just like a serve, and at 30 fps the true contact usually falls between two frames.",
  ],
  [
    "Some other strokes pass as serves",
    "Smashes, and one-handed backhands that finish with the racket overhead, can get through the serve check.",
  ],
  [
    "Hidden joints leave gaps",
    "A limb behind your body or the net, or out of frame, can leave a measurement or phase blank.",
  ],
  [
    "The ranges are rough guides",
    "The good and borderline ranges are based on coaching literature, not tailored to your age, height or level. Treat them as a starting point, not a verdict.",
  ],
];

export function LimitsList() {
  return (
    <ul className="space-y-2.5">
      {LIMITS.map(([title, detail]) => (
        <li key={title} className="text-sm">
          <p className="font-medium">{title}</p>
          <p className="text-ink-muted">{detail}</p>
        </li>
      ))}
    </ul>
  );
}

export function KnownLimits({ open = false }: { open?: boolean }) {
  return (
    <details open={open} className="group rounded-xl border border-border bg-surface p-4 [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-semibold">
        What this analysis can't do
        <svg viewBox="0 0 20 20" className="size-4 shrink-0 text-ink-muted transition-transform group-open:rotate-180" aria-hidden>
          <path d="m5 7.5 5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </summary>
      <div className="mt-3">
        <LimitsList />
      </div>
    </details>
  );
}
