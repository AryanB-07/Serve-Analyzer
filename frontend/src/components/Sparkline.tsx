/** A small line of scores (0-100) over time, with the good and borderline zones shaded. */
export function Sparkline({ scores, label }: { scores: number[]; label: string }) {
  if (scores.length < 2) return null;
  const w = 240;
  const h = 56;
  const x = (i: number) => (i / (scores.length - 1)) * (w - 8) + 4;
  const y = (score: number) => h - 4 - (score / 100) * (h - 8);
  const points = scores.map((s, i) => `${x(i).toFixed(1)},${y(s).toFixed(1)}`).join(" ");
  const last = scores[scores.length - 1]!;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-14 w-full max-w-60" role="img" aria-label={label} preserveAspectRatio="none">
      <rect x="0" y={y(100)} width={w} height={y(80) - y(100)} className="fill-good/10" />
      <rect x="0" y={y(80)} width={w} height={y(50) - y(80)} className="fill-warn/10" />
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" className="text-accent" vectorEffect="non-scaling-stroke" />
      <circle cx={x(scores.length - 1)} cy={y(last)} r="3" className="fill-accent" />
    </svg>
  );
}
