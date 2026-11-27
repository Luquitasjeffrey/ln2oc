import { AddressMaker } from "../components/AddressMaker";
import { FlowPlayer } from "../components/FlowPlayer";
import { SwapLedger } from "../components/SwapLedger";
import { communityFeeSat, fmt, pct, serviceFeeSat } from "../lib/fees";
import { useInstanceInfo } from "../lib/info";

const USES: [string, string, string][] = [
  ["Auto-envío", "De tu wallet caliente a frío",
   "Juntaste sats en Wallet of Satoshi, Phoenix o la wallet que uses. Te pagás a tu propia Lightning Address y quedan en tu cold wallet, sin abrir canales ni hacer un swap a mano."],
  ["P2P sin KYC", "Cobrás un trade, recibís en frío",
   "Comprás sats en un exchange P2P y, donde te pide cómo cobrar, ponés tu Lightning Address de ln2oc (por ejemplo, en Mostro). Cuando el vendedor libera, los sats van directo a tu cold wallet."],
  ["Cobros", "Cobrar cualquier cosa",
   "Una venta, una donación, un sueldo en sats: quien te paga usa Lightning y vos recibís on-chain. Para cada cobro podés armar una dirección nueva en segundos."],
];

const FAQ: [string, string][] = [
  ["¿Tengo que crear una cuenta?",
   "No. No hay registro, ni login, ni saldo a tu nombre. Lo único que le das al servicio es una dirección de recepción de tu cold wallet."],
  ["¿Qué pasa si el servicio no tiene sats on-chain para pagarme?",
   "Tu pago queda retenido en una hold invoice, sin cobrarse. Si no hay saldo, la invoice se cancela y el pago vuelve a tu wallet: no perdés nada."],
  ["¿Cuánto tarda?",
   "El pago se detecta en hasta un minuto y el payout sale en la misma vuelta, si la wallet del nodo no tiene otra tx sin confirmar. Llega a tu cold wallet con el próximo bloque, más o menos."],
  ["¿Por qué solo direcciones bc1q… o bc1p…?",
   "Una Lightning Address va en minúsculas, y las direcciones legacy (1…, 3…) distinguen mayúsculas: una wallet que las pase a minúsculas las rompe. SegWit y Taproot no tienen ese problema."],
  ["¿Es un swap atómico?",
   "No. Entre que el servicio cobra tu pago y publica tu tx pasan segundos en los que el operador tiene tu plata. Si algo falla justo ahí, el servicio se frena y una persona lo resuelve: el operador te debe el payout."],
];

export default function Landing() {
  const { info } = useInstanceInfo();
  const amount = 100_000;
  const fee = serviceFeeSat(amount, info.swap_fee_rate_bps);
  const community = communityFeeSat(amount, info.community_fee_rate_bps);
  return (
    <>
      {/* ------------------------------------------------ users */}
      <section className="hero" aria-labelledby="h-hero">
        <div className="hero-glow" aria-hidden="true" />
        <div className="wrap hero-in">
          <span className="chip">
            <span className="dot" /> Lightning → on-chain · sin cuentas
          </span>
          <h1 id="h-hero">
            Recibí por <span className="ln">Lightning</span>.<br />
            Llega a tu <span className="btc">cold wallet</span>.
          </h1>
          <p className="lede">
            Tu Lightning Address es tu dirección de Bitcoin. Te pagan por Lightning, o te pagás vos desde tu wallet caliente, y
            los sats aterrizan on-chain en una dirección cuyas llaves solo tenés vos.
          </p>
          <div className="hero-maker">
            <AddressMaker withPay />
            <div className="addr-legend">
              <span className="l1">tu dirección on-chain</span>
              <span className="l2">el dominio de ln2oc</span>
              <span>Se valida en tu navegador, con checksum.</span>
            </div>
          </div>
          <dl className="stats">
            <div><dt>Comisión</dt><dd>{pct(info.swap_fee_rate_bps)}</dd></div>
            <div><dt>Por swap</dt><dd>hasta {fmt(info.max_swap_sat)} sats</dd></div>
            <div><dt>Si falla</dt><dd>el pago vuelve</dd></div>
            <div><dt>Registro</dt><dd>ninguno</dd></div>
          </dl>
        </div>
      </section>

      <section className="wrap band" aria-labelledby="h-how">
        <div className="band-head">
          <span className="eyebrow">Para usuarios</span>
          <h2 id="h-how">Una dirección, un pago, sats en frío</h2>
        </div>
        <ol className="how">
          <li>
            <b>Armá tu Lightning Address</b>
            <span>Pegá una dirección de tu cold wallet y sumale <code>@{info.domain}</code>. Eso es todo.</span>
          </li>
          <li className="lnstep">
            <b>Pagá desde cualquier wallet Lightning</b>
            <span>O dásela a quien te paga. El pago queda retenido en una hold invoice: nadie lo cobró todavía.</span>
          </li>
          <li className="btcstep">
            <b>Llega on-chain</b>
            <span>Si el nodo tiene saldo, cobra y publica tu tx en el mismo paso. Si no, cancela y tu pago vuelve.</span>
          </li>
        </ol>
        <div className="anim">
          <FlowPlayer
            scenarios={["user"]}
            label="Animación para usuarios: armás tu Lightning Address, pagás desde tu wallet o cobrás un trade P2P, y los sats llegan a tu cold wallet. Si el nodo no tiene fondos, tus sats no se mueven."
          />
        </div>
      </section>

      <section className="wrap band" aria-labelledby="h-uses">
        <div className="band-head">
          <span className="eyebrow">Para qué sirve</span>
          <h2 id="h-uses">Tres formas de usarlo</h2>
        </div>
        <div className="cards3">
          {USES.map(([eb, title, text]) => (
            <div className="card" key={eb}>
              <span className="eyebrow">{eb}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="wrap band two" aria-label="Costos y confianza">
        <div>
          <span className="eyebrow">Costos</span>
          <h2>Un swap de {fmt(amount)} sats</h2>
          <SwapLedger />
        </div>
        <div>
          <span className="eyebrow">Confianza</span>
          <h2>En qué confiás y en qué no</h2>
          <ul className="trust">
            <li className="good">
              <b>Que el nodo tenga fondos:</b> no hace falta confiar. Si no hay sats on-chain, la hold invoice se cancela y tu
              pago vuelve.
            </li>
            <li className="good">
              <b>Que te paguen mal o dos veces:</b> la tx firmada se verifica (destino, monto, inputs) antes de publicarla, y
              un pago nunca se reintenta: ante cualquier duda el servicio se frena y lo revisa una persona.
            </li>
            <li className="care">
              <b>Los segundos entre el cobro y la publicación:</b> ahí el operador tiene tu plata. Si algo fallara, el
              servicio se frena y te debe el payout. Custodia por segundos, no por días.
            </li>
          </ul>
          <a className="more" href="/docs/usuarios/">Guía completa para usuarios →</a>
        </div>
      </section>

      <section className="wrap band" aria-labelledby="h-faq">
        <div className="band-head">
          <span className="eyebrow">Preguntas</span>
          <h2 id="h-faq">Lo que todos preguntan</h2>
        </div>
        <div className="faq">
          {FAQ.map(([q, a]) => (
            <details key={q}>
              <summary>{q}</summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------ community leaders */}
      <section className="comm-band" id="comunidades" aria-labelledby="h-comm">
        <div className="wrap">
          <div className="band-head">
            <span className="eyebrow comm-eb">Para community leaders</span>
            <h2 id="h-comm">Tus usuarios retiran on-chain. Vos te llevás una parte.</h2>
            <p className="lede read">
              Corrés un exchange P2P, una wallet o un sistema de pagos Lightning. Les ofrecés retiro on-chain a tus usuarios
              con ln2oc, sin construirlo, y {pct(info.community_fee_rate_bps)} de cada swap que llega por tu comunidad es
              tuyo. Para tus usuarios no cambia nada: pagan lo mismo y reciben lo mismo.
            </p>
          </div>
          <div className="comm-grid">
            <ol className="comm-steps">
              <li>
                <b>Hablás con el operador</b>
                <span>Te registra con un nombre: minúsculas, números y guiones. Sin firmar nada ni bloquear fondos.</span>
              </li>
              <li>
                <b>Sumás un parámetro</b>
                <span>Tu servicio resuelve la Lightning Address como siempre y agrega <code>?community=tu-comunidad</code>.</span>
              </li>
              <li>
                <b>Cobrás lo acumulado</b>
                <span>Cada swap exitoso suma. El operador te liquida por Lightning y lo registra.</span>
              </li>
            </ol>
            <div className="comm-side">
              <pre>
                <span className="c">{"# tu usuario te da su Lightning Address"}</span>
                {`\nGET https://${info.domain}/.well-known/lnurlp/bc1q…`}
                <span className="hl">{"?community=tu-comunidad"}</span>
              </pre>
              <div className="table-wrap">
                <table className="ledger">
                  <thead>
                    <tr><th>Comisión de un swap de {fmt(amount)} sats</th><th className="r">sats</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>Operador ({pct(info.swap_fee_rate_bps - info.community_fee_rate_bps)})</td><td className="r">{fmt(fee - community)}</td></tr>
                    <tr><td>Tu comunidad ({pct(info.community_fee_rate_bps)})</td><td className="r comm-t">{fmt(community)}</td></tr>
                  </tbody>
                  <tfoot>
                    <tr><td>Lo que paga tu usuario ({pct(info.swap_fee_rate_bps)})</td><td className="r">{fmt(fee)}</td></tr>
                  </tfoot>
                </table>
              </div>
            </div>
          </div>
          <div className="anim">
            <FlowPlayer
              scenarios={["community"]}
              label="Animación para comunidades: tu servicio agrega ?community= al pedir la invoice, tu usuario retira on-chain, la comisión se reparte entre el operador y tu comunidad, y el operador te liquida lo acumulado por Lightning."
            />
          </div>
          <div className="comm-cta">
            <a className="btn comm" href="/docs/comunidades/">Cómo integrarlo, en detalle</a>
            <span className="credit">
              Inspirado en <a href="https://github.com/lnp2pBot/bot">lnp2pBot</a>, de <a href="https://github.com/grunch">@grunch</a>.
            </span>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ the rest lives in the docs */}
      <section className="wrap band" aria-labelledby="h-more">
        <div className="band-head">
          <span className="eyebrow">¿Algo más?</span>
          <h2 id="h-more">Corré tu instancia o leé el código</h2>
        </div>
        <div className="cards2">
          <a className="card link" href="/docs/operadores/">
            <span className="eyebrow">Operadores</span>
            <h3>Poné el nodo, ganá la comisión</h3>
            <p>Capital en los dos lados, liquidez, cómo reponer el saldo on-chain y cómo registrar comunidades.</p>
            <span className="go">Docs para operadores →</span>
          </a>
          <a className="card link" href="/docs/desarrolladores/">
            <span className="eyebrow">Desarrolladores</span>
            <h3>GPLv3, Python, LND por gRPC</h3>
            <p>La API LNURL con el hook de comunidades, el flujo por dentro, cómo correrlo y testearlo.</p>
            <span className="go">Docs para desarrolladores →</span>
          </a>
        </div>
      </section>
    </>
  );
}
