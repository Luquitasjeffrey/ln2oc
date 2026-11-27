import { resolve } from "node:path";
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Multi-page static site: every page is a real index.html, so any static server (or the
// reverse proxy) serves it without SPA fallbacks. The site is "/", the docs live under /docs/.
const pages = ["", "docs", "docs/usuarios", "docs/comunidades", "docs/operadores", "docs/desarrolladores", "docs/flujo", "docs/arquitectura"];

/** A strict Content-Security-Policy in every built page: scripts and styles only from this
 * site, requests only to this site and the ln2oc API (/api/info and LNURL for the invoice
 * widget). A page that shows Lightning invoices should not run anything it did not ship. */
function csp(apiUrl: string): Plugin {
  const api = apiUrl ? new URL(apiUrl).origin : "";
  const policy = [
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    `connect-src 'self'${api ? ` ${api}` : ""}`,
    "base-uri 'none'",
    "form-action 'none'",
  ].join("; ");
  return {
    name: "ln2oc-csp",
    apply: "build", // the dev server injects inline scripts (HMR)
    transformIndexHtml: (html) =>
      html.replace("<head>", `<head>\n    <meta http-equiv="Content-Security-Policy" content="${policy}" />`),
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react(), csp(env.VITE_API_URL ?? "")],
    build: {
      rollupOptions: {
        input: Object.fromEntries(
          pages.map((p) => [p || "index", resolve(__dirname, p ? `${p}/index.html` : "index.html")]),
        ),
      },
    },
  };
});
