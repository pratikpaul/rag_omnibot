import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/healthz": "http://localhost:8000",
      "/thread":  "http://localhost:8000",
      "/chat":    "http://localhost:8000",
    },
  },
});
