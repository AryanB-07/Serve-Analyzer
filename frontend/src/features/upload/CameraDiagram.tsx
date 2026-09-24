/**
 * Top-down sketch: player on the baseline serving toward the net, camera on
 * a tripod to the side, 5-10 m away, looking straight across at the player.
 * Drawn with theme tokens so it works in light and dark mode.
 */
export function CameraDiagram() {
  return (
    <svg
      viewBox="0 0 320 220"
      role="img"
      aria-labelledby="camera-diagram-title camera-diagram-desc"
      className="w-full max-w-md text-ink"
    >
      <title id="camera-diagram-title">Camera placement, seen from above</title>
      <desc id="camera-diagram-desc">
        The player stands on the baseline serving toward the net. The camera is on a tripod to the
        player's side, 5 to 10 metres away, pointing straight at them so the whole body is in frame.
      </desc>
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0 10 5 0 10Z" fill="var(--ink-muted)" />
        </marker>
      </defs>

      {/* court: baseline, singles sideline, net */}
      <rect x="20" y="12" width="150" height="196" rx="4" fill="var(--surface-2)" stroke="var(--border)" />
      <line x1="20" y1="172" x2="170" y2="172" stroke="var(--ink-muted)" strokeWidth="2" />
      <line x1="20" y1="30" x2="170" y2="30" stroke="var(--ink)" strokeWidth="3" strokeDasharray="2 3" />
      <text x="95" y="24" textAnchor="middle" fontSize="10" fill="var(--ink-muted)">net</text>
      <text x="95" y="198" textAnchor="middle" fontSize="10" fill="var(--ink-muted)">baseline</text>

      {/* serve direction */}
      <line x1="95" y1="160" x2="95" y2="60" stroke="var(--ink-muted)" strokeWidth="1.5" strokeDasharray="4 4" markerEnd="url(#arrow)" />
      <text x="101" y="100" fontSize="10" fill="var(--ink-muted)">serve</text>

      {/* player */}
      <circle cx="95" cy="172" r="9" fill="var(--accent)" />
      <text x="95" y="176" textAnchor="middle" fontSize="10" fontWeight="700" fill="var(--on-accent)">P</text>

      {/* field of view */}
      <path d="M268 172 L110 138 L110 206 Z" fill="var(--accent)" opacity="0.12" />
      <line x1="266" y1="172" x2="112" y2="172" stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="5 4" />

      {/* camera on tripod */}
      <g transform="translate(270 172)">
        <rect x="0" y="-9" width="22" height="18" rx="3" fill="var(--ink)" />
        <path d="M0 -5 -8 -9 -8 9 0 5Z" fill="var(--ink)" />
        <circle cx="11" cy="0" r="4" fill="var(--bg)" />
      </g>
      <text x="281" y="198" textAnchor="middle" fontSize="10" fill="var(--ink-muted)">camera</text>
      <text x="281" y="210" textAnchor="middle" fontSize="10" fill="var(--ink-muted)">at hip height</text>

      {/* distance */}
      <line x1="112" y1="128" x2="266" y2="128" stroke="var(--ink-muted)" strokeWidth="1" markerStart="url(#arrow)" markerEnd="url(#arrow)" />
      <text x="189" y="122" textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--ink)">5–10 m</text>
    </svg>
  );
}
