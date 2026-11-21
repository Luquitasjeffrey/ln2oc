import type { ReactNode } from "react";
import { useInstanceInfo } from "../lib/info";

export type PageKey = "index" | "usuario" | "flujo" | "operadores" | "arquitectura";

const USER_LINKS: [PageKey, string, string][] = [
  ["usuario", "/usuario/", "Cómo se usa"],
  ["flujo", "/flujo/", "Animación"],
];
const OPERATOR_LINKS: [PageKey, string, string][] = [
  ["operadores", "/operadores/", "Operadores"],
  ["arquitectura", "/arquitectura/", "Arquitectura"],
];

export const REPO_URL = "https://github.com/Luquitasjeffrey/ln2oc";
// Who answers questions about this instance. Each operator sets their own at build time.
const TELEGRAM = (import.meta.env.VITE_CONTACT_TELEGRAM || "LucasJeffreyP2P").replace(/^@/, "");

function NavLink({ page, current, href, label }: { page: PageKey; current: PageKey; href: string; label: string }) {
  return (
    <a href={href} aria-current={page === current ? "page" : undefined}>
      {label}
    </a>
  );
}

export function Nav({ current }: { current: PageKey }) {
  return (
    <nav className="topnav" aria-label="Secciones">
      <a className="brand" href="/" aria-current={current === "index" ? "page" : undefined}>
        ln<b>2</b>oc
      </a>
      {USER_LINKS.map(([p, href, label]) => (
        <NavLink key={p} page={p} current={current} href={href} label={label} />
      ))}
      <span className="nav-sep" aria-hidden="true" />
      {OPERATOR_LINKS.map(([p, href, label]) => (
        <NavLink key={p} page={p} current={current} href={href} label={label} />
      ))}
      <span className="nav-sep" aria-hidden="true" />
      <a className="nav-icon" href={REPO_URL} target="_blank" rel="noopener noreferrer"
         aria-label="Código en GitHub" title="Código en GitHub">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" /></svg>
      </a>
      <a className="nav-icon" href={`https://t.me/${TELEGRAM}`} target="_blank" rel="noopener noreferrer"
         aria-label={`Consultas por Telegram: @${TELEGRAM}`} title={`Consultas por Telegram: @${TELEGRAM}`}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.9 4.3 18.7 19.4c-.2 1-.9 1.3-1.7.8l-4.7-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.8 8.6-7.8c.4-.3-.1-.5-.6-.2L6.6 13.2 2 11.8c-1-.3-1-1 .2-1.5L20.5 3.2c.9-.3 1.6.2 1.4 1.1z" /></svg>
      </a>
    </nav>
  );
}

export function Footer() {
  const { info, live } = useInstanceInfo();
  return (
    <footer className="site-footer">
      <span>ln2oc · LND v0.20 · gRPC · GPLv3</span>
      <span>
        Código: <a className="mono" href={REPO_URL}>github.com/Luquitasjeffrey/ln2oc</a>
      </span>
      <span className="mono" data-testid="version">
        {live ? `v${info.version} · commit ${info.commit} · ${info.network}` : "sin conexión con el servicio"}
      </span>
    </footer>
  );
}

function HaltBanner() {
  const { info, live } = useInstanceInfo();
  if (!live || !info.halted) return null;
  return (
    <div className="halt-banner" role="status">
      El servicio está frenado en este momento: no se emiten invoices nuevas. Tus sats no corren riesgo.
    </div>
  );
}

export function Layout({ current, children }: { current: PageKey; children: ReactNode }) {
  return (
    <div className="page">
      <Nav current={current} />
      <HaltBanner />
      {children}
      <Footer />
    </div>
  );
}
