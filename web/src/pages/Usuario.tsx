import { AddressMaker } from "../components/AddressMaker";
import { useSwapExample } from "../components/SwapLedger";
import { fmt } from "../lib/fees";

export default function Usuario() {
  const x = useSwapExample();
  const secs = x.info.invoice_poll_interval_seconds;
  const poll = secs >= 60 && secs % 60 === 0 ? (secs === 60 ? "1 minuto" : `${secs / 60} minutos`) : `${secs} segundos`;
  return (
    <>
      <header className="hero read">
        <div className="eyebrow">
          Paso a paso · usuario
        </div>
        <h1 style={{ marginTop: "0.9rem" }}>
          De tu wallet Lightning a tu cold wallet
        </h1>
        <p className="lede">
          Lo único que le das al servicio es una dirección de recepción. Tus llaves no salen nunca de tu cold wallet, y no hay cuenta ni saldo guardado a tu nombre. Está pensado para montos chicos: hasta 1.000.000 sats por swap.
        </p>
      </header>
      <div className="modes">
        <div className="mode">
          <span className="eyebrow">
            Modo 1
          </span>
          <h3>
            Recibir por Lightning
          </h3>
          <p>
            Publicás tu Lightning Address. Quien te paga usa cualquier wallet LN, y vos recibís on-chain sin tocar nada.
          </p>
        </div>
        <div className="mode">
          <span className="eyebrow">
            Modo 2
          </span>
          <h3>
            Mandarte a tu cold wallet
          </h3>
          <p>
            Juntaste sats en Wallet of Satoshi, Phoenix o la que uses. Te pagás a tu propia Lightning Address y los barrés a cold storage.
          </p>
        </div>
        <div className="mode">
          <span className="eyebrow">
            Modo 3
          </span>
          <h3>
            Cobrar un trade P2P
          </h3>
          <p>
            Comprás sats en un exchange P2P, como Mostro, y ponés tu Lightning Address de ln2oc como destino. Cuando el vendedor libera, llegan directo a frío.
          </p>
        </div>
      </div>
      <section className="read" aria-labelledby="h-steps">
        <h2 id="h-steps">
          Los pasos
        </h2>
        <ol className="steps">
          <li>
            {" "}
            <h3>
              Sacá una dirección de recepción de tu cold wallet
            </h3>
            {" "}
            <p>
              Sirve una dirección{" "}
              <code>
                bc1q…
              </code>
              {" "}(SegWit) o{" "}
              <code>
                bc1p…
              </code>
              {" "}(Taproot) de la red del servicio. Las legacy (
              <code>
                1…
              </code>
              ,{" "}
              <code>
                3…
              </code>
              ) no: distinguen mayúsculas, y una Lightning Address solo admite minúsculas. Alcanza con una wallet watch-only: nunca necesitás firmar nada.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Armá tu Lightning Address
            </h3>
            {" "}
            <p>
              Es tu dirección, una arroba y{" "}
              <code>{x.info.domain}</code>
              . No hay registro: la Lightning Address existe en cuanto la escribís. Pegá la dirección acá y se arma sola:
            </p>
            {" "}
            <AddressMaker />
            {" "}
            <p>
              El servicio vuelve a validar el checksum y la red: si la dirección no es válida, rechaza el pedido antes de emitir nada.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Pagá o compartila
            </h3>
            {" "}
            <p>
              Desde cualquier wallet con Lightning Address (LNURL-pay) elegís un monto dentro del mínimo y el máximo que publica el servicio. La wallet pide la invoice, y en la descripción ves a qué dirección va y cuántos sats llegan.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Tu pago queda retenido
            </h3>
            {" "}
            <p>
              La invoice es una{" "}
              <em>
                hold invoice
              </em>
              : el HTLC llega al nodo de ln2oc y queda trabado, en estado{" "}
              <code>
                ACCEPTED
              </code>
              . En tu wallet el pago aparece en curso. El servicio revisa los pagos pendientes cada {poll}, así que puede tardar hasta eso en verlo. Si la wallet on-chain del nodo tiene alguna tx sin confirmar (por ejemplo, el payout anterior), tu pago espera retenido hasta que confirme: no se cancela. Entonces el nodo solo verifica que tenga sats on-chain para pagarte. No firma nada todavía.
            </p>
            {" "}
            <span className="wallet pending">
              Pago en curso · hasta {poll}
            </span>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              El nodo cobra
            </h3>
            {" "}
            <p>
              Si hay saldo, el nodo libera el preimage y liquida la invoice. Tu wallet marca el pago como hecho. Si no hay saldo, cancela la invoice y tus sats nunca salen de tu wallet.
            </p>
            {" "}
            <span className="wallet done">
              Pagado · {fmt(x.amount)} sats
            </span>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Tus sats salen on-chain
            </h3>
            {" "}
            <p>
              Con el pago ya cobrado, el nodo arma, firma y publica tu transacción en el mismo paso. Tu cold wallet la ve en el mempool, y queda tuya de verdad con las confirmaciones.
            </p>
            {" "}
            <span className="wallet chain">
              +{fmt(x.payout)} sats · sin confirmar → 1 conf
            </span>
            {" "}
          </li>
        </ol>
      </section>
      <section className="read" aria-labelledby="h-fee">
        <h2 id="h-fee">
          Cuánto te llega
        </h2>
        <p>
          Dos descuentos y nada más: la comisión fija del servicio y la minería de tu transacción. La minería se calcula recién cuando se firma tu tx: su tamaño real por la tasa de ese momento.
        </p>
        <div className="formula">
          payout = ⌊ monto × (1 − {x.feePct}) ⌋ − tu parte de (minería estimada × 1,2)
        </div>
        <p>
          Por ejemplo, con {fmt(x.amount)} sats, una tx de {x.vbytes} vB{x.measured ? " (lo que pesó el último payout)" : ""} y {x.live ? "la tasa de ahora" : "una tasa de"}, {fmt(x.rate)} sat/vB: {fmt(x.amount)} − {fmt(x.fee)} − {fmt(x.miner)} ≈{" "}
          <b className="btc num">{fmt(x.payout)} sats</b>
          . El número exacto se sabe al enviar tu pago: el nodo estima la minería de la tx real a la tasa de ese momento, se le suma un 20 % y se reparte en partes iguales entre los pagos de esa tx. La minería se descuenta siempre de tu pago, y lo cobrado de más queda para el servicio: nunca pierde con ella. Si con tu parte el payout quedara por debajo del dust ({fmt(x.info.min_payout_sat)} sats), se cancela la invoice y tus sats no salen de tu wallet.
        </p>
        <p>
          Si llegaste por una <a href="/comunidades/">comunidad</a> (tu exchange o tu wallet integró ln2oc), no cambia nada para vos: la comisión es la misma, y la parte de la comunidad sale de lo que se queda el operador.
        </p>
      </section>
      <section aria-labelledby="h-what">
        <h2 id="h-what">
          Qué pasa si algo sale mal
        </h2>
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>
                  Situación
                </th>
                <th>
                  Qué ves en tu wallet LN
                </th>
                <th>
                  Tu plata
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  El nodo no tiene sats on-chain cuando llega tu pago
                </td>
                <td>
                  El pago falla
                </td>
                <td className="outcome-ok">
                  Nunca sale de tu wallet
                </td>
              </tr>
              <tr>
                <td>
                  Tu HTLC está a menos de 40 bloques de expirar
                </td>
                <td>
                  El pago falla
                </td>
                <td className="outcome-ok">
                  Vuelve entera
                </td>
              </tr>
              <tr>
                <td>
                  El servicio está caído cuando pagás
                </td>
                <td>
                  Pago en curso más tiempo
                </td>
                <td className="outcome-ok">
                  Sigue al volver el servicio; si no, LND lo cancela antes de expirar y vuelve
                </td>
              </tr>
              <tr>
                <td>
                  Pediste la invoice y no la pagaste
                </td>
                <td>
                  Nada
                </td>
                <td className="outcome-ok">
                  Expira sola en 1 hora
                </td>
              </tr>
              <tr>
                <td>
                  Algo falla después del cobro: no se puede armar o publicar tu tx (muy raro)
                </td>
                <td>
                  Pagado
                </td>
                <td className="outcome-owed">
                  El servicio se frena y el operador te debe el payout: lo resuelve a mano
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <section className="read" aria-labelledby="h-mostro">
        <h2 id="h-mostro">
          Cobrar un trade P2P en frío
        </h2>
        <p>
          Cualquier exchange P2P que te pague a una Lightning Address sirve. Un ejemplo es Mostro, que corre sobre Nostr, no pide KYC y usa hold invoices para el escrow, el mismo mecanismo que ln2oc.
        </p>
        <ol className="steps">
          <li>
            {" "}
            <h3>
              Armá tu Lightning Address de ln2oc
            </h3>
            {" "}
            <p>
              Una dirección nueva de tu cold wallet más{" "}
              <code>@{x.info.domain}</code>
              . Usá una por trade para no reutilizar direcciones.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Tomá o publicá una orden de compra
            </h3>
            {" "}
            <p>
              En el exchange P2P que uses. Cuando te pida dónde recibir los sats, pegá tu Lightning Address.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Pagás el fiat y el vendedor libera
            </h3>
            {" "}
            <p>
              El exchange le paga a tu Lightning Address, ln2oc retiene ese pago y te manda los sats on-chain.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Los sats llegan a tu cold wallet
            </h3>
            {" "}
            <p>
              Nunca pasaron por una wallet caliente tuya: del escrow del exchange a tus llaves en frío.
            </p>
            {" "}
          </li>
        </ol>
        <div className="callout ln">
          <span className="eyebrow">
            Costos y montos
          </span>
          <p>
            Del monto del trade se descuentan la comisión del exchange, la de ln2oc y la minería. En compras chicas la minería pesa más. Si ln2oc no puede pagar on-chain, el pago del exchange a tu Lightning Address falla y los sats no quedan en ln2oc; qué pasa después depende del exchange (Mostro, por ejemplo, reintenta el pago).
          </p>
        </div>
      </section>
      <section className="read" aria-labelledby="h-priv">
        <h2 id="h-priv">
          Privacidad: ojo con reutilizar la dirección
        </h2>
        <div className="callout btc">
          <span className="eyebrow">
            Reuso de direcciones
          </span>
          <p>
            Tu Lightning Address{" "}
            <em>
              contiene
            </em>
            {" "}tu dirección on-chain. Cada pago a esa misma Lightning Address cae en la misma dirección, y cualquiera que la conozca puede seguir todo lo que recibe en la cadena.
          </p>
          <p>
            Para cobros recurrentes, rotá: sacá una dirección nueva de tu cold wallet y armá una Lightning Address nueva. Es gratis e instantáneo, porque no hay nada que registrar.
          </p>
        </div>
        <p>
          El operador ve tu dirección y los montos, porque los necesita para pagarte. No ve ni necesita nada más: ni tus llaves, ni tu xpub, ni tu identidad.
        </p>
      </section>
      <div className="pager">
        <a href="/">
          ← ln2oc
        </a>
        <a href="/comunidades/">
          Community leaders →
        </a>
      </div>
    </>
  );
}
