import { useState } from "react";
import { Sequence } from "../components/Sequence";
import { FAILED, PARTICIPANTS, SUCCESS } from "../lib/diagrams";
import { fmt, pct } from "../lib/fees";
import { useInstanceInfo } from "../lib/info";

const CARDS: [string, string, string][] = [
  ["/docs/usuarios/", "Usuarios", "Armar tu Lightning Address, cuánto te llega, qué pasa si algo falla."],
  ["/docs/comunidades/", "Community leaders", "Ofrecer retiro on-chain a tus usuarios con un parámetro y llevarte una parte."],
  ["/docs/operadores/", "Operadores", "Capital, liquidez, reponer el saldo on-chain, registrar y pagar comunidades."],
  ["/docs/desarrolladores/", "Desarrolladores", "La API LNURL, el hook de comunidades, correrlo y testearlo."],
];

export default function Docs() {
  const { info } = useInstanceInfo();
  const [tab, setTab] = useState<"ok" | "fail">("ok");
  return (
    <>
      <header className="hero read">
        <div className="eyebrow">Docs · cómo funciona</div>
        <h1 style={{ marginTop: "0.8rem" }}>De la Lightning Address a tu cold wallet</h1>
        <p className="lede">
          La Lightning Address es la dirección on-chain de destino: <code>&lt;dirección bitcoin&gt;@{info.domain}</code>.
          Quien paga recibe una hold invoice; cuando el pago llega, ln2oc lo cobra y publica tu payout on-chain en la
          misma vuelta. Si no puede pagarte on-chain, cancela la invoice y el pago vuelve.
        </p>
      </header>

      <h2 id="secuencia">El swap, paso a paso</h2>
      <p className="read">
        Un swap de 100.000 sats con la comisión de {pct(info.swap_fee_rate_bps)}. La comunidad es opcional: si el pedido
        trae <code>?community=nombre</code>, {pct(info.community_fee_rate_bps)} de esa comisión es suyo. Para quien paga no
        cambia nada.
      </p>
      <div className="tabs" role="tablist" aria-label="Escenario">
        <button role="tab" className="ok-tab" aria-selected={tab === "ok"} onClick={() => setTab("ok")}>
          Swap exitoso
        </button>
        <button role="tab" className="bad-tab" aria-selected={tab === "fail"} onClick={() => setTab("fail")}>
          Sin saldo: reembolso
        </button>
      </div>
      {tab === "ok" ? (
        <Sequence title="Swap exitoso: de la Lightning Address al payout on-chain, con la parte de la comunidad." participants={PARTICIPANTS} steps={SUCCESS} />
      ) : (
        <Sequence title="Swap fallido: el nodo no tiene saldo on-chain, la hold invoice se cancela y el pago vuelve." participants={PARTICIPANTS} steps={FAILED} />
      )}
      <div className="legend-row">
        <span className="l-ln">Lightning</span>
        <span className="l-btc">on-chain</span>
        <span className="l-comm">comunidad</span>
        <span className="l-bad">reembolso</span>
        <span>línea punteada: respuesta</span>
      </div>
      <div className="callout read">
        <span className="eyebrow">Lo que no se ve en el diagrama</span>
        <p>
          Cualquier cosa fuera de las reglas de negocio (saldo, dust, tasa máxima) frena el servicio y deja el swap en
          revisión manual: nunca se reintenta un pago a ciegas. Si algo falla después del cobro, el operador te debe el
          payout y lo resuelve una persona. Con cualquier tx de la wallet sin confirmar no se paga nada: ~1 payout por
          bloque, y todos los pagos retenidos van en la misma tx.
        </p>
      </div>
      <p className="read">
        La animación con cada llamada al nodo está en <a href="/docs/flujo/">El swap en movimiento</a>; los componentes y
        la máquina de estados, en <a href="/docs/arquitectura/">Arquitectura</a>.
      </p>

      <h2 id="publicos">Por público</h2>
      <div className="doc-cards">
        {CARDS.map(([href, title, text]) => (
          <a className="doc-card" href={href} key={href}>
            <h3>{title}</h3>
            <p>{text}</p>
            <span className="go">{href} →</span>
          </a>
        ))}
      </div>

      <h2 id="supuestos">Supuestos de esta versión</h2>
      <p className="read" style={{ color: "var(--muted)" }}>
        Lo que ln2oc da por hecho hoy. Si alguno no se cumple en tu caso, este no es tu servicio, o todavía no.
      </p>
      <ol className="sup-list read">
        <li className="key">
          <span>
            <b>Se consigue mejor ratio de conversión de Lightning a on-chain con cantidades grandes.</b> Pasar 5.000.000
            sats de una vez cuesta, en porcentaje, bastante menos que de a 100.000: quizás 0,2 % o menos. El margen es
            esa diferencia contra la comisión (ver <a href="/docs/operadores/#h-refill">cómo reponer el saldo on-chain</a>).
            Si no se cumpliera, el valor sería la comodidad.
          </span>
        </li>
        <li>
          <span>
            <b>Montos chicos.</b> Hasta {fmt(info.max_swap_sat)} sats por swap, justo donde convertir por tu cuenta sale caro.
          </span>
        </li>
        <li>
          <span>
            <b>Comisión de {pct(info.swap_fee_rate_bps)}.</b> Cada operador la elige. La minería del payout la paga el
            usuario, a la tasa del momento, y no es parte del porcentaje.
          </span>
        </li>
        <li>
          <span>
            <b>El operador repone el saldo on-chain a mano.</b> Junta volumen en Lightning y lo convierte en bloque.
          </span>
        </li>
        <li>
          <span>
            <b>Servicio aislado.</b> Nodo LND y dominio dedicados, con poca plata adentro. Nunca un nodo principal.
          </span>
        </li>
        <li>
          <span>
            <b>Cualquiera puede levantar su instancia.</b> GPLv3: tu nodo, tu dominio, tu comisión.
          </span>
        </li>
        <li>
          <span>
            <b>Custodia por segundos, no swap atómico.</b> Entre el cobro y la publicación de tu tx, el operador tiene tu
            plata. Si algo falla ahí, el servicio se frena y te debe el payout.
          </span>
        </li>
      </ol>
    </>
  );
}
