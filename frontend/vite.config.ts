import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "serve" ? "/" : "/static/frontend/",
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    cors: { origin: /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/ },
  },
  build: {
    outDir: "dist",
    manifest: "manifest.json",
    emptyOutDir: true,
    rolldownOptions: {
      input: {
        listing: fileURLToPath(new URL("./src/main.tsx", import.meta.url)),
        styles: fileURLToPath(new URL("./scss/main.scss", import.meta.url)),
      },
    },
  },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost/brand/" } },
    setupFiles: ["./src/test/setup.ts"],
    clearMocks: true,
    restoreMocks: true,
  },
}));
