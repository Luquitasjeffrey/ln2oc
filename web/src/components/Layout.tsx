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
    </nav>
  );
}

export function Footer() {
  const { info, live } = useInstanceInfo();
  return (
    <footer className="site-footer">
      <span>ln2oc · LND v0.20 · gRPC · GPLv3</span>
      <span>
        Código: <a className="mono" href="https://github.com/Luquitasjeffrey/ln2oc">github.com/Luquitasjeffrey/ln2oc</a>
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
