import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const API_URL = process.env.VITE_API_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // During development the browser talks to Vite, and Vite forwards API calls to FastAPI.
    proxy: {
      "/api": API_URL,
      "/health": API_URL,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
