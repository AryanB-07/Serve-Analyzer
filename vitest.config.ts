// Running Vitest from the repository root (the editor's default folder) would skip
// frontend/vite.config.ts: no jsdom, no setup file, and it would try to run the Playwright
// browser tests in frontend/e2e. This points it at the frontend project instead. No imports, so
// it needs nothing installed at the root.
export default {
  test: {
    projects: ["frontend"],
  },
};
