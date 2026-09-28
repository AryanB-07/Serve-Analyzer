const AUTH_PAGES = ["/login", "/signup"];

/**
 * Where to go after signing in. Only paths inside this app are allowed, so a
 * crafted ?next= link can't bounce the user to another site ("//evil.example",
 * "https://…") or loop back to the sign-in page.
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return "/";
  const path = raw.split(/[?#]/)[0] ?? raw;
  return AUTH_PAGES.includes(path) ? "/" : raw;
}

/** The ?next= query for sending someone at ``path`` to sign in, then back. */
export function nextParam(path: string): string {
  return path === "/" ? "" : `?next=${encodeURIComponent(path)}`;
}
