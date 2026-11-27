import { REPO_URL } from "../components/Layout";

const CARDS: [string, string, string, string, string, boolean][] = [
  [REPO_URL, "Repositorio", "GitHub",
   "Código, README con la configuración completa, tests de integración y guías de testnet4 y producción.",
   "github.com/Luquitasjeffrey/ln2oc", true],
  ["/arquitectura/", "Código", "Arquitectura",
   "Qué módulo habla con quién, la máquina de estados, los hilos y las reglas que protegen los fondos.", "/arquitectura/", false],
  ["/flujo/", "Animación", "El swap en movimiento",
   "La plata y el código, cuadro por cuadro: del HTLC retenido al bloque minado, y el caso sin saldo.", "/flujo/", false],
  ["/comunidades/", "Integración", "Hook de comunidades",
   "Cómo un servicio Lightning asocia los swaps de sus usuarios a su comunidad con ?community=.", "/comunidades/", false],
];

export default function Desarrolladores() {
  return (
    <>
      <header className="hero read">
        <div className="eyebrow">Desarrolladores</div>
        <h1 style={{ marginTop: "0.9rem" }}>El código es abierto</h1>
        <p className="lede">
          ln2oc es GPLv3: Python 3.12, FastAPI, SQLite y la API gRPC de LND v0.20, con Docker Compose. Leelo, corré tu instancia o integralo desde tu servicio.
        </p>
      </header>

      <div className="links">
        {CARDS.map(([href, eyebrow, title, text, go, primary]) => (
          <a className={primary ? "link-card primary" : "link-card"} href={href} key={href}>
            <span className="eyebrow">{eyebrow}</span>
            <h3>{title}</h3>
            <p>{text}</p>
            <span className="go">{go} →</span>
          </a>
        ))}
      </div>

      <section className="read" aria-labelledby="h-api">
        <h2 id="h-api">La API</h2>
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr><th>Endpoint</th><th>Qué hace</th></tr>
            </thead>
            <tbody>
              <tr>
                <td><code>{"GET /.well-known/lnurlp/{dirección}"}</code></td>
                <td>LNURL-pay, paso 1 (LUD-06/16). Opcional: <code>?community=&lt;handle&gt;</code>, que se valida y viaja al callback.</td>
              </tr>
              <tr>
                <td><code>GET /lnurlp/cb?btc_address=…&amp;amount=…</code></td>
                <td>Paso 2: emite la hold invoice. Acepta también <code>&amp;community=</code>.</td>
              </tr>
              <tr>
                <td><code>GET /api/info</code></td>
                <td>Parámetros públicos de la instancia: red, comisión (<code>swap_fee_rate_bps</code>, <code>community_fee_rate_bps</code>), mínimos, minería del momento, versión.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>
          Los errores vuelven con su código HTTP (400, 502, 503) y <code>{'{"status":"ERROR","reason":…}'}</code> en el cuerpo, con <code>Access-Control-Allow-Origin: *</code>.
        </p>
      </section>

      <section className="read" aria-labelledby="h-run">
        <h2 id="h-run">Correrlo y testearlo</h2>
        <pre>
          {"python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt\nPYTHON=.venv/bin/python scripts/gen_protos.sh\n.venv/bin/python -m pytest tests -q   "}
          <span className="c">{"# integración contra Polar (regtest)"}</span>
          {"\ncp .env.dev .env && docker compose up -d --build"}
        </pre>
        <p>
          Los tests son de integración contra una red regtest de Polar: pagos reales, hold invoices reales y tx en bitcoind. La filosofía del proyecto: si algo no es como se espera, el servicio se frena en vez de atajar casos bordes.
        </p>
      </section>

      <div className="pager">
        <a href="/docs/operadores/">← Operadores</a>
        <a href="/docs/flujo/">El swap en movimiento →</a>
      </div>
    </>
  );
}
