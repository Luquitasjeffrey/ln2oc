import { FlowPlayer } from "../components/FlowPlayer";

export default function Flujo() {
  return (
    <>
      <header className="hero read">
        <div className="eyebrow">Docs · por dentro</div>
        <h1 style={{ marginTop: "0.8rem" }}>El swap en movimiento</h1>
        <p className="lede">
          Por dentro: arriba la plata, abajo el estado de la invoice en LND y el del swap en ln2oc, con cada llamada real
          al nodo. También están las versiones cortas de la portada, para usuarios y comunidades.
        </p>
      </header>
      <div style={{ marginTop: "1.75rem" }}>
        <FlowPlayer
          scenarios={["ok", "fail", "user", "community"]}
          label="Animación del swap por dentro: hold invoice, pago retenido, chequeo de saldo, settle, firma y publicación del payout, o cancelación si no hay saldo."
        />
      </div>
      <div className="legend-row">
        <span className="l-ln">sats por Lightning</span>
        <span className="l-btc">sats on-chain</span>
        <span>azul: señales del código</span>
        <span className="l-bad">rechazo o reembolso</span>
      </div>
      <p className="read">
        El mismo flujo como diagrama de secuencia: <a href="/docs/#secuencia">Cómo funciona</a>.
      </p>
      <div className="pager">
        <a href="/docs/desarrolladores/">← Desarrolladores</a>
        <a href="/docs/arquitectura/">Arquitectura →</a>
      </div>
    </>
  );
}
