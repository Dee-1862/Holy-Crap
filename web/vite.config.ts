import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const environment = (globalThis as {
  process?: { env?: Record<string, string | undefined> };
}).process?.env;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": environment?.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
    },
  },
});
