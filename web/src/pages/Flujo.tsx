import { useEffect, useRef } from "react";
import { mountFlow } from "../flujo/animation.js";

export default function Flujo() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => (ref.current ? mountFlow(ref.current) : undefined), []);
  return (
    <div ref={ref}>
      <h1>
        El swap en movimiento
      </h1>
      <p className="sub">
        Primero, lo que ve el usuario: una dirección, un pago, sats en frío. Después, por dentro: arriba la plata, abajo el estado de la invoice en LND y el del swap en ln2oc, con cada llamada real al nodo.
      </p>
      <div className="stage">
        <canvas id="cv" width="1280" height="720" role="img" aria-label="Animación del swap: el pagador obtiene una hold invoice, paga, el HTLC queda retenido, el nodo bloquea un UTXO y firma el payout, liquida la invoice con el preimage y publica la transacción hacia la cold wallet." />
      </div>
      <div className="controls">
        <button id="play" type="button" aria-label="Pausar">
          ❚❚ Pausa
        </button>
        <button id="restart" type="button">
          ↺ Reiniciar
        </button>
        <div className="seg" role="group" aria-label="Escenario">
          <button id="sc-user" type="button" aria-pressed="true">
            Lo que ve el usuario
          </button>
          <button id="sc-ok" type="button" aria-pressed="false">
            Por dentro: swap exitoso
          </button>
          <button id="sc-fail" type="button" aria-pressed="false">
            Por dentro: sin saldo
          </button>
        </div>
        <div className="scrub">
          <input id="scrub" type="range" min="0" max="39" step="0.01" defaultValue="0" aria-label="Posición en la animación" />
          <span className="time" id="time">
            0,0 s
          </span>
        </div>
      </div>
      <div className="chapters" id="chapters" aria-label="Pasos" />
      <div className="legend">
        <span className="y">
          sats por Lightning
        </span>
        <span className="g">
          sats on-chain
        </span>
        <span className="b">
          señales del código
        </span>
        <span className="gr">
          confirmado
        </span>
        <span className="r">
          rechazo o reembolso
        </span>
      </div>
      <div className="pager">
        <a href="/operadores/">
          ← Paso a paso del operador
        </a>
        <a href="/arquitectura/">
          Arquitectura →
        </a>
      </div>
    </div>
  );
}
