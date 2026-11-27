import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Multi-page static site: every page is a real index.html, so any static server (or the
// reverse proxy) serves it without SPA fallbacks.
const pages = ["index", "usuario", "comunidades", "operadores", "desarrolladores", "flujo", "arquitectura"];

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: Object.fromEntries(
        pages.map((p) => [p, resolve(__dirname, p === "index" ? "index.html" : `${p}/index.html`)]),
      ),
    },
  },
});
