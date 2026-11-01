import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": { target: "http://127.0.0.1:8251", changeOrigin: false } } },
  build: { sourcemap: false, chunkSizeWarningLimit: 1600 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"], exclude: ["e2e/**", "node_modules/**"] },
} as any);
