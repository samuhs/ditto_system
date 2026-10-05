/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Node's process, without pulling in @types/node for one variable.
declare const process: { env: Record<string, string | undefined> };

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        // `make up-local` points this at the API on IPv6 loopback ([::1]).
        target: process.env.VITE_API_PROXY ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
    clearMocks: true,
    // An unhandled error (e.g. a render crash not caught by any test assertion)
    // must fail the run instead of only being logged — see issue #22.
    dangerouslyIgnoreUnhandledErrors: false,
  },
});
