export default function Operador() {
  return (
    <>
      <header className="hero read">
        <div className="eyebrow">
          Paso a paso · operador
        </div>
        <h1 style={{ marginTop: "0.9rem" }}>
          Ser la contraparte de cada swap
        </h1>
        <p className="lede">
          En cada swap vos ponés los sats on-chain y recibís los mismos sats por Lightning, más la comisión. Para eso necesitás capital en los dos lados antes de recibir el primer pago. Cualquiera puede levantar su propia instancia, con su nodo, su dominio y su comisión.
        </p>
      </header>
      <section className="read" aria-labelledby="h-iso">
        <div className="callout btc">
          <span className="eyebrow" id="h-iso">
            Regla número uno
          </span>
          <p>
            <b>
              ln2oc va en su propio nodo y con su propio dominio.
            </b>
            {" "}Es un servicio aislado: no corre adentro de otro programa ni comparte nodo con nada.
          </p>
          <p>
            Montá un nodo LND dedicado solo a ln2oc, con el capital de trabajo de los swaps y nada más. No uses tu nodo principal, ni uno de routing, ni uno con mucha plata, ni uno que uses para otra cosa: el servicio firma transacciones solo, y si algo sale mal, el daño tiene que quedar acotado a ese nodo.
          </p>
          <p>
            Si querés sumarlo a un proyecto Lightning (una wallet, una plataforma P2P, un comercio), desplegalo al lado, como servicio separado, con su nodo y su dominio.
          </p>
        </div>
        <div className="callout">
          <span className="eyebrow">
            Supuestos de esta versión
          </span>
          <p>
            <b>
              #1: se consigue mejor ratio de conversión de Lightning a on-chain con cantidades grandes.
            </b>
            {" "}De ahí sale tu margen. Además: montos chicos, hasta 1.000.000 sats por swap. Comisión del 0,7 %, configurable. Nodo y dominio dedicados. Reponer el saldo on-chain es manual, convirtiendo en bloque. Cualquiera puede levantar su instancia. La lista completa está en el{" "}
            <a href="/#h-sup">
              índice
            </a>
            .
          </p>
        </div>
      </section>
      <section aria-labelledby="h-cap">
        <h2 id="h-cap" className="read">
          Cómo se mueve tu capital
        </h2>
        <p className="read">
          Cada swap es un intercambio de lugar de tus propios sats: salen de tu wallet on-chain hacia la cold wallet del usuario, y entran a tus canales por Lightning. Tu total crece por la comisión, pero el capital migra de un tanque al otro.
        </p>
        <figure>
          <div className="canvas">
            <svg className="cap" viewBox="0 0 900 380" role="img" aria-label="Cada swap vacía la wallet on-chain del nodo hacia las cold wallets de los usuarios y llena el lado local de los canales Lightning consumiendo liquidez entrante; un rebalanceo periódico devuelve sats de Lightning a on-chain.">
              <defs>
                <marker id="ah-btc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="head-btc" />
                </marker>
                <marker id="ah-ln" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="head-ln" />
                </marker>
                <marker id="ah-ink" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="head-ink" />
                </marker>
              </defs>
              <text x="160" y="40" textAnchor="middle" className="lbl">
                Wallet on-chain del nodo
              </text>
              <rect x="90" y="56" width="140" height="220" rx="6" className="frame" />
              <rect x="92" y="150" width="136" height="124" rx="4" className="btcfill" />
              <text x="160" y="300" textAnchor="middle" className="small">
                baja con cada payout
              </text>
              <text x="740" y="40" textAnchor="middle" className="lbl">
                Canales Lightning
              </text>
              <rect x="670" y="56" width="140" height="220" rx="6" className="frame" />
              <rect x="672" y="58" width="136" height="96" rx="4" className="inbound" />
              <rect x="672" y="154" width="136" height="120" rx="4" className="lnfill" />
              <text x="822" y="108" className="small">
                entrante
              </text>
              <text x="822" y="124" className="small">
                (de tus peers)
              </text>
              <text x="822" y="216" className="small">
                local
              </text>
              <text x="822" y="232" className="small">
                (tuyo)
              </text>
              <text x="740" y="300" textAnchor="middle" className="small">
                el local sube, el entrante baja
              </text>
              <rect x="380" y="62" width="160" height="52" rx="8" className="box" />
              <text x="460" y="84" textAnchor="middle" className="lbl">
                Pagadores
              </text>
              <text x="460" y="102" textAnchor="middle" className="small">
                wallets Lightning
              </text>
              <path d="M540 88 L664 120" className="lnline" markerEnd="url(#ah-ln)" />
              <text x="604" y="90" textAnchor="middle" className="num lnt">
                +100.000
              </text>
              <rect x="380" y="200" width="160" height="52" rx="8" className="box" />
              <text x="460" y="222" textAnchor="middle" className="lbl">
                Cold wallets
              </text>
              <text x="460" y="240" textAnchor="middle" className="small">
                de los usuarios
              </text>
              <path d="M236 212 L374 226" className="btcline" markerEnd="url(#ah-btc)" />
              <text x="304" y="200" textAnchor="middle" className="num btct">
                −99.169 payout
              </text>
              <path d="M236 250 L326 280" className="btcline" markerEnd="url(#ah-btc)" />
              <text x="334" y="290" className="num btct">
                −131 minería
              </text>
              <path d="M740 284 C 740 372, 160 372, 160 284" className="loop" markerEnd="url(#ah-ink)" />
              <text x="450" y="368" textAnchor="middle" className="small">
                rebalanceo periódico: Lightning → on-chain
              </text>
            </svg>
          </div>
          <figcaption>
            Un swap de 100.000 sats con la minería de hoy, 1 sat/vB: el lado on-chain pierde 99.300 sats (99.169 de payout y 131 de minería, que paga el usuario) y el lado Lightning gana 100.000. Te quedan exactamente los 700 sats de la comisión: la minería no te suma ni te resta. Sin rebalancear, en algún momento se te acaba el tanque on-chain o la liquidez entrante, y los swaps se empiezan a cancelar.
          </figcaption>
        </figure>
      </section>
      <section className="read" aria-labelledby="h-manual">
        <h2 id="h-manual">
          El saldo on-chain lo administrás vos
        </h2>
        <p>
          En esta versión, ln2oc no rebalancea solo. Cada swap te suma sats en Lightning y te saca sats on-chain, y reponer el tanque on-chain es tarea del operador, a mano: cada uno busca cómo convertir grandes cantidades de Lightning a on-chain, o va cerrando canales.
        </p>
        <p>
          La premisa del negocio es que convertir en bloque sale más barato, en porcentaje, que de a poco. Pasar 5.000.000 sats de una vez puede costar bastante menos que pasar 100.000. Un servicio como este puede cobrar alrededor de 0,7 % por swap chico, mientras que una conversión grande se puede conseguir por 0,2 % o menos. Esa diferencia es tu margen.
        </p>
        <p>
          Si en tu caso no consiguieras convertir en bloque más barato, el servicio no cerraría por costo, o directamente no sería viable. Lo que queda para cobrar es la comodidad: hay usuarios dispuestos a pagar, por ejemplo, 1 % por no tener que resolverlo solos. Por eso la comisión es configurable.
        </p>
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>
                  Ejemplo: 50 swaps de 100.000 sats
                </th>
                <th className="r">
                  sats
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  Volumen total por Lightning
                </td>
                <td className="r ln">
                  5.000.000
                </td>
              </tr>
              <tr>
                <td>
                  Comisiones cobradas a los usuarios (0,7 %)
                </td>
                <td className="r">
                  +35.000
                </td>
              </tr>
              <tr>
                <td>
                  Reponer on-chain en un solo bloque (0,2 %)
                </td>
                <td className="r">
                  −10.000
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td>
                  Margen antes de otros costos
                </td>
                <td className="r ok">
                  ≈ 25.000
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p style={{ color: "var(--muted)", fontSize: "var(--step--1)" }}>
          Porcentajes ilustrativos y sin minería: la de cada payout la paga el usuario y no entra en esta cuenta. La comisión se configura con{" "}
          <code>
            SWAP_FEE_RATE
          </code>
          ; el costo de reponer depende de cómo lo hagas, mirá{" "}
          <a href="#h-refill">
            las opciones
          </a>
          .
        </p>
        <div className="callout">
          <span className="eyebrow">
            Fuera de esta versión
          </span>
          <p>
            Automatizar la reposición del saldo on-chain no está resuelto y no es parte de esta versión. Mientras tanto: vigilá el saldo, juntá volumen en Lightning y convertilo de a mucho, cerrando canales en forma cooperativa o con un swap-out grande con quien te dé mejor precio.
          </p>
        </div>
      </section>
      <section aria-labelledby="h-refill">
        <h2 id="h-refill" className="read">
          Cómo reponer el saldo on-chain
        </h2>
        <p className="read">
          Opciones para convertir lo que juntaste en Lightning a on-chain, ordenadas por costo con volumen. Los porcentajes no incluyen minería: la de cada payout la paga el usuario y no entra en nuestro 0,7 %, y la de la reposición es un costo fijo chico (hoy, con el mempool a 1 sat/vB, unos cientos de sats por operación).
        </p>
        <div className="table-wrap">
          <table className="ledger refill">
            <thead>
              <tr>
                <th>
                  Opción
                </th>
                <th>
                  Custodia
                </th>
                <th className="r">
                  Costo del proveedor
                </th>
                <th>
                  Volumen
                </th>
                <th>
                  A tener en cuenta
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <b>
                    Ya tengo sats on-chain y me sirve pasarme a Lightning
                  </b>
                </td>
                <td>
                  <span className="pill ok-pill">
                    no custodial
                  </span>
                </td>
                <td className="r num">
                  0 %
                </td>
                <td>
                  Lo que tengas y quieras tener en Lightning
                </td>
                <td>
                  Fondeás el nodo con tus propios sats on-chain y los swaps te los devuelven en Lightning, más la comisión. No hay a quién pagarle, pero no escala: se termina cuando no querés más sats en Lightning.
                </td>
              </tr>
              <tr>
                <td>
                  <b>
                    Cierre cooperativo de canales
                  </b>
                </td>
                <td>
                  <span className="pill ok-pill">
                    no custodial
                  </span>
                </td>
                <td className="r num">
                  0 %
                </td>
                <td>
                  Lo que tengas del lado local del canal
                </td>
                <td>
                  Pagás una sola tx (~200 vB) sin importar el monto: la mejor escala. El costo escondido es volver a conseguir esa liquidez entrante.
                </td>
              </tr>
              <tr>
                <td>
                  <b>
                    Exchanges
                  </b>
                  <br />
                  <span className="muted">
                    Kraken, Bitfinex, OKX, Binance…
                  </span>
                </td>
                <td>
                  <span className="pill bad-pill">
                    custodial · KYC
                  </span>
                </td>
                <td className="r num">
                  ≤ 0,2 %
                  <br />
                  <span className="muted">
                    variable por volumen
                  </span>
                </td>
                <td>
                  Alto; con límites por operación en Lightning
                </td>
                <td>
                  El depósito por Lightning suele ser gratis y el retiro on-chain cobra una comisión fija, así que cuanto más movés, menor el %. Usalo de paso: depositás, retirás y no dejás saldo.
                </td>
              </tr>
              <tr>
                <td>
                  <b>
                    Lightning Loop Out
                  </b>
                  <br />
                  <span className="muted">
                    Lightning Labs
                  </span>
                </td>
                <td>
                  <span className="pill ok-pill">
                    no custodial
                  </span>
                </td>
                <td className="r num">
                  0,05 – 0,5 %
                </td>
                <td>
                  Desde ~250.000 sats; sin máximo publicado
                </td>
                <td>
                  Submarine swap con{" "}
                  <code>
                    loopd
                  </code>
                  {" "}al lado de tu LND. En sus docs: ~0,17 % en 300.000 sats y ~0,33 % en 1.000.000. Suma routing hasta su nodo (casi 0 con canal directo) y un prepay de 30.000 sats. El % no baja con el monto.
                </td>
              </tr>
              <tr>
                <td>
                  <b>
                    FixedFloat
                  </b>
                </td>
                <td>
                  <span className="pill warn-pill">
                    custodial · sin cuenta
                  </span>
                </td>
                <td className="r num">
                  0,5 – 1 %
                </td>
                <td>
                  Límites por orden
                </td>
                <td>
                  0,5 % con tasa flotante y 1 % con tasa fija. Tus sats quedan en sus manos unos minutos.
                </td>
              </tr>
              <tr>
                <td>
                  <b>
                    Swap servers de Electrum
                  </b>
                  <br />
                  <span className="muted">
                    mercado sobre Nostr
                  </span>
                </td>
                <td>
                  <span className="pill ok-pill">
                    no custodial
                  </span>
                </td>
                <td className="r num">
                  ~0,5 – 1 %
                </td>
                <td>
                  Según la liquidez de cada proveedor
                </td>
                <td>
                  Cada proveedor fija su comisión: el servidor de Electrum viene en 0,5 % por defecto y otros cobran 1 %. Se usa desde la wallet Electrum.
                </td>
              </tr>
              <tr>
                <td>
                  <b>
                    Wallets custodiales
                  </b>
                  <br />
                  <span className="muted">
                    p. ej. Rizful
                  </span>
                </td>
                <td>
                  <span className="pill warn-pill">
                    custodial
                  </span>
                </td>
                <td className="r num">
                  ~0,5 %
                </td>
                <td>
                  Chico; mínimo 5.000 sats
                </td>
                <td>
                  Mandás por Lightning a la wallet y enviás on-chain desde ahí.
                </td>
              </tr>
              <tr>
                <td>
                  <b>
                    Boltz
                  </b>
                </td>
                <td>
                  <span className="pill ok-pill">
                    no custodial
                  </span>
                </td>
                <td className="r num">
                  0,5 %
                </td>
                <td>
                  —
                </td>
                <td>
                  <b>
                    Caído.
                  </b>
                  {" "}Suspendió los swaps en agosto de 2026 y hoy no responde.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="callout">
          <span className="eyebrow">
            Criterio
          </span>
          <p>
            Gana el que consigue{" "}
            <b>
              mejor % con el volumen que necesitás
            </b>
            . A costo parecido, primero lo self-custodial. Lo custodial, exchanges incluidos, está bien en su justa medida: de paso, por el tiempo mínimo y sin dejar saldos.
          </p>
          <p>
            Con eso, el orden práctico hoy es:{" "}
            <b>
              tus propios sats on-chain
            </b>
            {" "}mientras te sirva tenerlos en Lightning, que es gratis pero no escala;{" "}
            <b>
              cerrar canales
            </b>
            {" "}cuando de todos modos tenés que reciclar liquidez; un{" "}
            <b>
              exchange
            </b>
            {" "}para mover volumen grande por 0,2 % o menos;{" "}
            <b>
              Loop Out
            </b>
            {" "}cuando querés quedarte sin custodia y te cierra su 0,05 – 0,5 %. Lo que cobra 0,5 % o más solo sirve para montos chicos: ahí ya no queda margen contra el 0,7 %.
          </p>
        </div>
        <p className="read" style={{ color: "var(--muted)", fontSize: "var(--step--1)" }}>
          Datos relevados en noviembre de 2026, de la documentación de Lightning Labs y de Electrum, y de comparativas públicas para el resto. Los precios cambian: cotizá siempre antes de operar (
          <code>
            loop quote out {"<"}monto{">"}
          </code>
          {" "}en Loop).
        </p>
      </section>
      <section aria-labelledby="h-size">
        <h2 id="h-size" className="read">
          Cuánto capital necesitás
        </h2>
        <div className="sizing">
          <div className="size">
            <span className="eyebrow btc">
              On-chain
            </span>
            <h3>
              Lo que vas a pagar entre rebalanceos
            </h3>
            <p>
              Como mínimo, el swap más grande que aceptes más su minería, y no mucho más: en un nodo dedicado va solo el capital de trabajo.{" "}
              <code>
                MAX_SWAP_SAT
              </code>
              {" "}viene en 1.000.000 sats: el servicio apunta a montos chicos. LND además reserva 10.000 sats por canal anchor (hasta 100.000), que no se pueden gastar.
            </p>
          </div>
          <div className="size">
            <span className="eyebrow ln">
              Lightning
            </span>
            <h3>
              Liquidez entrante
            </h3>
            <p>
              Para que te puedan pagar, tus canales necesitan saldo del lado remoto. Abrir canales no alcanza: esos sats son tuyos y son salientes. Comprá liquidez entrante o pedile a peers bien conectados que te abran canales.
            </p>
          </div>
          <div className="size">
            <span className="eyebrow">
              Forma de los UTXOs
            </span>
            <h3>
              Varios medianos, no uno gigante
            </h3>
            <p>
              Se paga un lote a la vez (todos los pagos retenidos juntos, en una tx, hasta MAX_PAYOUT_BATCH) y por defecto solo se gastan UTXOs confirmados. Con un único UTXO, el cambio queda sin confirmar y pagás más o menos un lote por bloque. Con muchos UTXOs chicos, la tx pesa más y los swaps se cancelan por fee.
            </p>
          </div>
        </div>
      </section>
      <section className="read" aria-labelledby="h-steps">
        <h2 id="h-steps">
          Los pasos
        </h2>
        <ol className="steps">
          <li>
            {" "}
            <h3>
              Montá un nodo dedicado
            </h3>
            {" "}
            <p>
              Bitcoin Core más un LND v0.20.x nuevo, que va a hacer solo esto, con gRPC accesible para el servicio. Los{" "}
              <code>
                .proto
              </code>
              {" "}del repo están fijados a esa versión.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Fondeá la wallet on-chain del nodo
            </h3>
            {" "}
            <p>
              Mandá desde tu cold storage a direcciones del nodo, en varias salidas, y esperá confirmaciones.
            </p>
            {" "}
            <pre><span className="c">{"# una dirección por UTXO que quieras crear"}</span>{"\nlncli newaddress p2tr"}</pre>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Conseguí liquidez entrante
            </h3>
            {" "}
            <p>
              Como mínimo, el volumen que pensás procesar entre rebalanceos, en canales con buena conectividad para que los pagadores encuentren ruta hasta vos.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Configurá ln2oc
            </h3>
            {" "}
            <pre><span className="c">{"# .env"}</span>{"\nLND_GRPC_HOST=127.0.0.1:10009\nLND_MACAROON_PATH=/ruta/admin.macaroon\nLND_TLS_CERT_PATH=/ruta/tls.cert\nBITCOIN_NETWORK=mainnet\nSWAP_FEE_RATE=0.007      "}<span className="c">{"# 0,7 % por defecto, configurable"}</span>{"\nMIN_SWAP_SAT=10000\nMAX_SWAP_SAT=1000000     "}<span className="c">{"# montos chicos: hasta 1.000.000 sats"}</span>{"\nDOMAIN=ln2oc.com\nEXTERNAL_URL=https://ln2oc.com\nFRONTEND_URL=https://www.ln2oc.com   "}<span className="c">{"# el sitio, en otro servidor"}</span>{"\nINVOICE_POLL_INTERVAL_SECONDS=60  "}<span className="c">{"# cada cuánto mira los pagos"}</span></pre>
            {" "}
            <p>
              La configuración se valida al arrancar: un valor fuera de rango frena el servicio en vez de dejarlo andar mal configurado.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Levantá el servicio
            </h3>
            {" "}
            <pre>{"docker compose up -d --build"}</pre>
            {" "}
            <p>
              Corre un único proceso. Al arrancar toma un lock exclusivo, verifica el schema de la DB, se niega a seguir si hay swaps en{" "}
              <code>
                MANUAL_REVIEW
              </code>
              {" "}o si LND está en otra red, y arranca el worker: en un solo hilo mueve los swaps y consulta las invoices pendientes cada minuto.
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Publicalo con HTTPS
            </h3>
            {" "}
            <p>
              LNURL exige HTTPS. Poné un reverse proxy con TLS delante del puerto 8000 y hacé que{" "}
              <code>
                DOMAIN
              </code>
              {" "}y{" "}
              <code>
                EXTERNAL_URL
              </code>
              {" "}coincidan con él. El sitio web va aparte, en su propio servidor (la imagen{" "}
              <code>web/</code>
              {" "}es un nginx con archivos estáticos): el servicio no sirve el sitio, solo redirige{" "}
              <code>GET /</code>
              {" "}a{" "}
              <code>FRONTEND_URL</code>
              . El sitio lee los valores de tu instancia de{" "}
              <code>/api/info</code>
              .
            </p>
            {" "}
          </li>
          <li>
            {" "}
            <h3>
              Operá y reponé el saldo on-chain
            </h3>
            {" "}
            <p>
              Mirá tu saldo on-chain y tu liquidez entrante. En esta versión la reposición es manual: cuando juntaste volumen en Lightning, convertilo en bloque a on-chain (cerrando canales o con un swap-out grande). Ese costo sale de tu margen: tenelo en cuenta al fijar la comisión.
            </p>
            {" "}
          </li>
        </ol>
      </section>
      <section className="read" aria-labelledby="h-review">
        <h2 id="h-review">
          Cuando el servicio se frena solo
        </h2>
        <div className="callout">
          <span className="eyebrow">
            MANUAL_REVIEW
          </span>
          <p>
            Si se rompe un invariante que protege fondos, el swap pasa a{" "}
            <code>
              MANUAL_REVIEW
            </code>
            {" "}con el motivo en la columna{" "}
            <code>
              error
            </code>
            , y el proceso termina. Mientras quede un swap así, el servicio no arranca. Es a propósito: preferimos una caída a una pérdida.
          </p>
          <p>
            Si el error dice{" "}
            <code>
              USER IS OWED
            </code>
            , ya cobraste por Lightning y el usuario no recibió su payout. Si hay una tx firmada en{" "}
            <code>
              raw_tx
            </code>
            , revisá por qué la rechazó la red; si no la hay, falló el fondeo y hay que armar el pago a mano. Pagale al usuario y recién entonces cerrá el caso en la DB.
          </p>
        </div>
      </section>
      <section className="read" aria-labelledby="h-todo">
        <h2 id="h-todo">
          Antes de mainnet
        </h2>
        <p>
          Esto todavía no está hecho, y con plata real conviene tenerlo:
        </p>
        <ul className="todo">
          <li>
            Un macaroon con permisos mínimos en lugar del admin.
          </li>
          <li>
            Alertas activas cuando el servicio se frena o LND no responde: hoy solo quedan en los logs.
          </li>
          <li>
            Backup continuo de la SQLite, que guarda los preimages y las tx firmadas, y backup de canales de LND (SCB).
          </li>
          <li>
            Un tope de payouts por hora o por día y un kill switch manual.
          </li>
          <li>
            Una prueba completa en testnet con wallets reales.
          </li>
        </ul>
      </section>
      <div className="pager">
        <a href="/usuario/">
          ← Paso a paso del usuario
        </a>
        <a href="/flujo/">
          El swap en movimiento →
        </a>
      </div>
    </>
  );
}
