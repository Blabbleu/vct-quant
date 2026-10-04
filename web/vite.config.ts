import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies the read-only API (and the local logo cache) to a node
// backend: :8000 by default, or API_ORIGIN (e.g. the UI worktree's backend).
declare const process: { env: Record<string, string | undefined> };
const api = process.env.API_ORIGIN || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": api, "/logos": api } },
  build: { outDir: "dist", emptyOutDir: true },
});
