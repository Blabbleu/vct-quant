import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies the read-only API to the node backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", emptyOutDir: true },
});
