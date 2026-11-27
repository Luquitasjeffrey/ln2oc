import { FlowPlayer } from "../components/FlowPlayer";
import { Sequence } from "../components/Sequence";
import { PARTICIPANTS, SUCCESS } from "../lib/diagrams";
import { communityFeeSat, fmt, pct, serviceFeeSat } from "../lib/fees";
import { useInstanceInfo } from "../lib/info";

export default function Comunidades() {
  const { info } = useInstanceInfo();
  const amount = 100_000;
  const fee = serviceFeeSat(amount, info.swap_fee_rate_bps);
  const community = communityFeeSat(amount, info.community_fee_rate_bps);
  const share = pct(info.community_fee_rate_bps);
  return (
    <>
      <header className="hero read">
        <div className="eyebrow">Paso a paso · community leaders</div>
        <h1 style={{ marginTop: "0.9rem" }}>Retiro on-chain para tus usuarios, sin construirlo</h1>
        <p className="lede">
          Si corrés un exchange P2P (por ejemplo, un nodo de Mostro), una wallet o un sistema de pagos Lightning, tus usuarios pueden retirar on-chain con ln2oc. Vos aportás los usuarios, y por cada swap que llega por tu comunidad te corresponde un % de incentivo (en esta instancia, {share}; por defecto es 0,1 %).
        </p>
      </header>

      <section className="read" aria-labelledby="h-earn">
        <h2 id="h-earn">Qué ganás</h2>
        <p>
          De la comisión de {pct(info.swap_fee_rate_bps)} de cada swap, <b>{share} es para tu comunidad</b>. Sale de lo que se queda el operador: tus usuarios pagan exactamente lo mismo que cualquier otro.
        </p>
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr><th>Un swap de {fmt(amount)} sats</th><th className="r">sin comunidad</th><th className="r">con tu comunidad</th></tr>
            </thead>
            <tbody>
              <tr><td>Comisión total ({pct(info.swap_fee_rate_bps)})</td><td className="r">{fmt(fee)}</td><td className="r">{fmt(fee)}</td></tr>
              <tr><td>Para el operador</td><td className="r">{fmt(fee)}</td><td className="r">{fmt(fee - community)}</td></tr>
              <tr><td>Para tu comunidad ({share})</td><td className="r">0</td><td className="r ln">{fmt(community)}</td></tr>
            </tbody>
            <tfoot>
              <tr><td>Para tu usuario, antes de minería</td><td className="r btc">{fmt(amount - fee)}</td><td className="r btc">{fmt(amount - fee)}</td></tr>
            </tfoot>
          </table>
        </div>
        <p style={{ color: "var(--muted)", fontSize: "var(--step--1)" }}>
          Son los porcentajes de esta instancia: cada operador fija los suyos. Tu parte se cuenta solo para los swaps que terminaron bien: una invoice que no se pagó o un pago reembolsado no suman nada.
        </p>
      </section>

      <section className="read" aria-labelledby="h-steps">
        <h2 id="h-steps">Cómo crear tu comunidad</h2>
        <ol className="steps">
          <li>
            <h3>Contactá al operador</h3>
            <p>
              Hablá con el operador de la instancia (en este sitio, por el Telegram de arriba). Contale qué servicio corrés y dejale un contacto: Telegram, mail, lo que uses. Ese contacto es solo para coordinar los pagos y no se publica.
            </p>
          </li>
          <li>
            <h3>El operador te registra y te da tu handle</h3>
            <p>
              El handle es el nombre de tu comunidad: minúsculas, números y guiones, hasta 32 caracteres. Por ejemplo, <code>mi-comunidad</code>. No hay que firmar nada ni bloquear fondos.
            </p>
          </li>
          <li>
            <h3>Agregá el handle en tu integración</h3>
            <p>
              Tu servicio resuelve la Lightning Address de tu usuario como siempre y le agrega <code>?community=&lt;handle&gt;</code> a la URL de LNURL-pay. ln2oc lo arrastra al callback, y el swap queda asociado a tu comunidad.
            </p>
            <pre>
              <span className="c">{`# tu usuario te da: bc1q…@${info.domain}`}</span>
              {`\nGET https://${info.domain}/.well-known/lnurlp/bc1q…?community=mi-comunidad\n`}
              <span className="c">{`# → callback: https://${info.domain}/lnurlp/cb?btc_address=bc1q…&community=mi-comunidad`}</span>
              {"\n"}
              <span className="c">{"# tu servicio le suma &amount=<msat> como siempre y paga la invoice"}</span>
            </pre>
            <p>
              Si el handle no existe o está mal escrito, la respuesta es un error 400: te enterás enseguida en vez de perder tu parte sin saberlo.
            </p>
          </li>
          <li>
            <h3>Cobrá lo acumulado</h3>
            <p>
              El operador lleva la cuenta de cada swap de tu comunidad y te liquida lo adeudado a mano. Le pasás una invoice o una Lightning Address y te paga por Lightning.
            </p>
          </li>
        </ol>
      </section>

      <section aria-labelledby="h-seq">
        <h2 id="h-seq" className="read">El recorrido completo</h2>
        <p className="read">
          Desde que tu servicio pide la invoice con tu nombre hasta que el operador te liquida. El reembolso, cuando el nodo no tiene saldo, está en <a href="/docs/#secuencia">Cómo funciona</a>: en ese caso tu comunidad no cobra nada, porque no hubo swap.
        </p>
        <Sequence title="Un retiro que llega por tu comunidad: la Lightning Address, la hold invoice, el payout on-chain y tu parte de la comisión." participants={PARTICIPANTS} steps={SUCCESS} />
        <div style={{ marginTop: "2rem" }}>
          <FlowPlayer
            scenarios={["community"]}
            label="Animación para comunidades: tu servicio agrega ?community= al pedir la invoice, tu usuario retira on-chain, la comisión se reparte entre el operador y tu comunidad, y el operador te liquida lo acumulado por Lightning."
          />
        </div>
      </section>
      <section className="read" aria-labelledby="h-users">
        <h2 id="h-users">Para tus usuarios no cambia nada</h2>
        <ul className="facts">
          <li><b>Usan la misma Lightning Address</b>: <code>bc1q…@{info.domain}</code>. El handle lo agrega tu servicio, no ellos.</li>
          <li><b>Pagan lo mismo y reciben lo mismo</b>: tu parte sale de la comisión del operador.</li>
          <li>
            <b>Una wallet común sigue funcionando</b> sin el parámetro: es un hook cooperativo sobre LNURL, opcional. Sin <code>?community=</code> la respuesta es idéntica a la de siempre, y el operador se queda la comisión completa.
          </li>
        </ul>
      </section>

      <section className="read" aria-labelledby="h-trust">
        <h2 id="h-trust">En qué confiás</h2>
        <ul className="facts">
          <li className="care">
            <b>En el operador, para la cuenta y el pago.</b> Lo adeudado es una deuda de palabra: el operador la calcula desde los swaps registrados y te la paga a mano. Hoy no hay un pago automático.
          </li>
          <li className="care">
            <b>En que nadie se cuelgue de tu handle.</b> El handle viaja en la URL y es público: cualquiera podría agregarlo a sus propios swaps. Lo peor que pasa es que tu comunidad cobre de más, nunca de menos.
          </li>
        </ul>
        <div className="callout ln">
          <span className="eyebrow">De dónde viene la idea</span>
          <p>
            El modelo de comunidades está inspirado en <a href="https://github.com/lnp2pBot/bot">lnp2pBot</a>, de <a href="https://github.com/grunch">@grunch</a>: las comunidades que traen usuarios comparten la comisión de las operaciones.
          </p>
        </div>
      </section>

      <div className="pager">
        <a href="/docs/usuarios/">← Usuarios</a>
        <a href="/docs/operadores/">Operadores →</a>
      </div>
    </>
  );
}
