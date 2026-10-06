import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Read without @types/node: this file is type-checked with the browser's types.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Same-origin in dev: the browser talks to /api and Vite forwards to FastAPI,
    // so there is no CORS setup and signed URLs can be relative.
    proxy: {
      "/api": {
        // Override when port 8000 is taken: VITE_API_TARGET=http://127.0.0.1:8010 npm run dev
        target: env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
