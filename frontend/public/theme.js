// Applies the saved light/dark theme before the app renders, so the page doesn't flash.
// A separate file rather than inline, so the Content-Security-Policy can forbid inline scripts.
try {
  const saved = localStorage.getItem("theme");
  if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
} catch {}
