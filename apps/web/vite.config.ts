import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://localhost:8000",
      "/ingress": "http://localhost:8000",
      "/work-items": "http://localhost:8000",
      "/runs": "http://localhost:8000",
      "/bootstrap": "http://localhost:8000",
      "/knowledge": "http://localhost:8000",
      "/scheduler": "http://localhost:8000",
      "/settings": "http://localhost:8000",
      "/audit": "http://localhost:8000"
    }
  }
});
