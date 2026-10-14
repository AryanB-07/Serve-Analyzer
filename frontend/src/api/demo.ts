export const DEMO_IDS = ["demo-serve-1", "demo-serve-2"] as const;

/** The analysis the public demo page (/demo) shows. */
export const PUBLIC_DEMO_ID = DEMO_IDS[0];

export function isDemoId(id: string): boolean {
  return (DEMO_IDS as readonly string[]).includes(id);
}

/**
 * Where a demo analysis's files live: real pipeline output for the CC BY 4.0 sample clip
 * (scripts/make_mock_fixtures.py), shipped with the site in public/mock, so the demo needs no
 * account, database or worker.
 */
export function demoFile(id: string, file: "summary.json" | "result.json" | "frames.json"): string {
  return `/mock/${id}/${file}`;
}
