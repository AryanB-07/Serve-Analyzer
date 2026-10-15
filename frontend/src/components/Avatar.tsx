/** A profile picture, or initials (or a person outline) when there isn't one. Decorative: the
 * name it belongs to is always shown or announced next to it. */
export function Avatar({ url, name, size = "md" }: { url: string | null | undefined; name: string | null | undefined; size?: "sm" | "md" | "lg" }) {
  const box = { sm: "size-8 text-xs", md: "size-12 text-base", lg: "size-24 text-3xl" }[size];
  const initials = (name ?? "")
    .split(/[\s_]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
  if (url) {
    return <img src={url} alt="" className={`${box} shrink-0 rounded-full bg-surface-2 object-cover`} aria-hidden />;
  }
  return (
    <span
      className={`${box} inline-grid shrink-0 place-items-center rounded-full bg-accent/15 font-semibold text-accent`}
      aria-hidden
    >
      {initials || (
        <svg viewBox="0 0 24 24" className="size-3/5" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" />
        </svg>
      )}
    </span>
  );
}
