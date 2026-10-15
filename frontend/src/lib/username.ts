/**
 * Username rules, the same as the API's (serve_api/schemas.py): 3 to 20 lowercase letters,
 * numbers and underscores, case-insensitive, and a few reserved names. The API has the final
 * say; this lets the form explain a problem as it's typed.
 */
export const RESERVED_USERNAMES = new Set([
  "admin", "administrator", "api", "app", "help", "me", "mod", "moderator", "null", "privacy",
  "profile", "root", "serve", "serveanalyzer", "serve_analyzer", "settings", "staff", "support",
  "system", "terms", "undefined", "user", "users",
]);

export function normaliseUsername(value: string): string {
  return value.trim().replace(/^@+/, "").toLowerCase();
}

export function usernameProblem(username: string): string | null {
  if (username.length < 3 || username.length > 20) return "Usernames are 3 to 20 characters.";
  if (!/^[a-z0-9_]+$/.test(username)) return "Use only letters, numbers and underscores.";
  if (RESERVED_USERNAMES.has(username)) return "That username is reserved.";
  return null;
}
