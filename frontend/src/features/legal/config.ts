/**
 * Facts the Privacy Policy and Terms depend on. Fill in the bracketed values before launch
 * (see docs/launch-checklist.md), and have both documents reviewed for where you operate.
 *
 * TERMS_VERSION must match serve_api/auth.py TERMS_VERSION (tests/test_legal_sync.py checks it).
 * Change both whenever either document changes materially; signups record which version they
 * accepted.
 */
export const TERMS_VERSION = "2026-10-06";
export const LAST_UPDATED = "6 October 2026";

export const LEGAL = {
  /** Who runs the service: your name, or your company's legal name. */
  operator: "[Operator name]",
  /** Where people can reach you about privacy and the terms. */
  contactEmail: "[privacy@your-domain]",
  /** Whose laws govern the Terms, e.g. "the State of California, USA". */
  governingLaw: "[jurisdiction]",
  /** Where the servers and storage are, e.g. "the United States (AWS us-east-1)". */
  hostingRegion: "[hosting region]",
  /** Must match SERVE_API_UPLOAD_RETENTION_DAYS. */
  uploadRetentionDays: 30,
  /** Must match the database's automated backup retention (RDS defaults to 7 days). */
  backupRetentionDays: 7,
  minimumAge: 13,
} as const;

/** True while any placeholder above is still unfilled. */
export const HAS_PLACEHOLDERS = Object.values(LEGAL).some((v) => typeof v === "string" && v.startsWith("["));
