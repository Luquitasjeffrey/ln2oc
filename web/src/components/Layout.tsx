import { useEffect, useState, type ReactNode } from "react";
import { useInstanceInfo } from "../lib/info";

export type PageKey =
  | "index"
  | "docs"
  | "usuarios"
  | "comunidades"
  | "operadores"
  | "desarrolladores"
  | "flujo"
  | "arquitectura";

type Who = "usuario" | "comunidad" | "operador" | "dev";

// "¿Quién sos?": users and community leaders live on the landing, the rest in the docs.
const WHO: [Who, string, string][] = [
  ["usuario", "/", "Usuario"],
  ["comunidad", "/#comunidades", "Community leader"],
  ["operador", "/docs/operadores/", "Operador"],
  ["dev", "/docs/desarrolladores/", "Desarrollador"],
];
const WHO_OF: Partial<Record<PageKey, Who>> = {
  usuarios: "usuario",
  comunidades: "comunidad",
  operadores: "operador",
  flujo: "operador",
  desarrolladores: "dev",
  arquitectura: "dev",
};

// The docs: their own section, with their own sidebar.
const DOCS: { group: string; items: [PageKey, string, string][] }[] = [
  { group: "Empezar", items: [["docs", "/docs/", "Cómo funciona"]] },
  {
    group: "Por público",
    items: [
      ["usuarios", "/docs/usuarios/", "Usuarios"],
      ["comunidades", "/docs/comunidades/", "Community leaders"],
      ["operadores", "/docs/operadores/", "Operadores"],
      ["desarrolladores", "/docs/desarrolladores/", "Desarrolladores"],
    ],
  },
  {
    group: "Por dentro",
    items: [
      ["flujo", "/docs/flujo/", "El swap en movimiento"],
      ["arquitectura", "/docs/arquitectura/", "Arquitectura"],
    ],
  },
];

export const REPO_URL = "https://github.com/Luquitasjeffrey/ln2oc";
// Who answers questions about this instance. Each operator sets their own at build time.
const TELEGRAM = (import.meta.env.VITE_CONTACT_TELEGRAM || "LucasJeffreyP2P").replace(/^@/, "");

/** On the landing, which of the two audiences is on screen (#comunidades or above). */
function useLandingWho(enabled: boolean): Who {
  const [who, setWho] = useState<Who>("usuario");
  useEffect(() => {
    if (!enabled) return;
    const el = document.getElementById("comunidades");
    if (!el) return;
    const onScroll = () => setWho(el.getBoundingClientRect().top < window.innerHeight * 0.4 ? "comunidad" : "usuario");
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [enabled]);
  return who;
}

function Logo() {
  return (
    <svg className="logo-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" className="lm-bg" />
      <path d="M17.5 5 9 18h6l-1.5 9L23 13h-6.2z" className="lm-bolt" />
    </svg>
  );
}

function Icons() {
  return (
    <>
      <a className="icon" href={REPO_URL} target="_blank" rel="noopener noreferrer" aria-label="Código en GitHub" title="Código en GitHub">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" /></svg>
      </a>
      <a className="icon" href={`https://t.me/${TELEGRAM}`} target="_blank" rel="noopener noreferrer"
         aria-label={`Consultas por Telegram: @${TELEGRAM}`} title={`Consultas por Telegram: @${TELEGRAM}`}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.9 4.3 18.7 19.4c-.2 1-.9 1.3-1.7.8l-4.7-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.8 8.6-7.8c.4-.3-.1-.5-.6-.2L6.6 13.2 2 11.8c-1-.3-1-1 .2-1.5L20.5 3.2c.9-.3 1.6.2 1.4 1.1z" /></svg>
      </a>
    </>
  );
}

export function Header({ current }: { current: PageKey }) {
  const landingWho = useLandingWho(current === "index");
  const who = current === "index" ? landingWho : WHO_OF[current];
  const inDocs = current !== "index";
  return (
    <header className={`site-head${inDocs ? " in-docs" : ""}`}>
      <div className="head-row">
        <a className="brand" href="/" title="ln2oc: Lightning Network to on-chain">
          <Logo />
          <span className="brand-name">ln<b>2</b>oc</span>
          {inDocs && <span className="docs-badge">Docs</span>}
        </a>
        <nav className="who" aria-label="¿Quién sos?">
          <span className="who-q">¿Quién sos?</span>
          <div className="who-seg">
            {WHO.map(([w, href, label]) => (
              <a key={w} href={href} aria-current={who === w ? "true" : undefined}>
                {label}
              </a>
            ))}
          </div>
        </nav>
        <div className="head-end">
          <a className={`docs-link${inDocs ? " on" : ""}`} href="/docs/">Docs</a>
          <Icons />
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  const { info, live } = useInstanceInfo();
  return (
    <footer className="site-footer">
      <div className="foot-brand">
        <Logo />
        <span>
          <b>ln2oc</b> · Lightning Network to on-chain
          <br />
          <span className="dim">GPLv3 · LND v0.20 · cualquiera puede correr su instancia</span>
        </span>
      </div>
      <nav className="foot-links" aria-label="Pie">
        <a href="/">Inicio</a>
        <a href="/docs/">Docs</a>
        <a href={REPO_URL}>GitHub</a>
        <a href={`https://t.me/${TELEGRAM}`}>Telegram</a>
      </nav>
      <span className="mono dim" data-testid="version">
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

function NetworkBanner() {
  const { info, live } = useInstanceInfo();
  if (!live || info.network === "mainnet") return null;
  return (
    <div className="net-banner" role="status">
      Esta instancia corre en <b>{info.network}</b>: sats de prueba, no de verdad.
    </div>
  );
}

/** The site (landing): wide, its own header. */
export function SiteLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Header current="index" />
      <NetworkBanner />
      <HaltBanner />
      <main className="site">{children}</main>
      <div className="wrap">
        <Footer />
      </div>
    </>
  );
}

/** The docs: sidebar + reading column, visibly a different place from the site. */
export function DocsLayout({ current, children }: { current: PageKey; children: ReactNode }) {
  return (
    <div className="docs-root">
      <Header current={current} />
      <NetworkBanner />
      <HaltBanner />
      <div className="docs">
        <aside className="docs-side" aria-label="Documentación">
          {DOCS.map((g) => (
            <div className="side-group" key={g.group}>
              <span className="side-h">{g.group}</span>
              {g.items.map(([p, href, label]) => (
                <a key={p} href={href} aria-current={p === current ? "page" : undefined}>
                  {label}
                </a>
              ))}
            </div>
          ))}
        </aside>
        <main className="docs-main">{children}</main>
      </div>
      <div className="wrap">
        <Footer />
      </div>
    </div>
  );
}
