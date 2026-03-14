import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": apiTarget,
      "/ingress": apiTarget,
      "/work-items": apiTarget,
      "/runs/": apiTarget,
      "/backfill": apiTarget,
      "/knowledge/": apiTarget,
      "/scheduler/": apiTarget,
      "/settings/": apiTarget,
      "/audit/": apiTarget
    }
  }
});
