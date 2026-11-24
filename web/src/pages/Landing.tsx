import { AddressMaker } from "../components/AddressMaker";
import { SwapLedger } from "../components/SwapLedger";

export default function Landing() {
  return (
    <>
      <header className="hero">
        <div className="eyebrow">
          ln2oc · Lightning → on-chain
        </div>
        <h1 style={{ marginTop: "1rem" }}>
          Recibí por Lightning. Que llegue directo a tu cold wallet.
        </h1>
        <p className="lede read">
          Tu Lightning Address es tu dirección de Bitcoin. Te pagan por Lightning, o te pagás vos mismo desde tu wallet caliente, y los sats aterrizan on-chain en una dirección cuyas llaves solo tenés vos. Sin cuentas, sin registro, sin saldos de custodia esperando.
        </p>
        <AddressMaker />
        <div className="addr-legend">
          <span className="l1">
            tu dirección on-chain (la de tu cold wallet)
          </span>
          <span className="l2">
            el dominio de ln2oc
          </span>
          <span>
            Se valida acá, en tu navegador, con checksum.
          </span>
        </div>
      </header>
      <section className="assumptions" aria-labelledby="h-sup">
        <div>
          <span className="eyebrow">
            Esta versión
          </span>
          <h2 id="h-sup" style={{ marginTop: "0.5rem" }}>
            Supuestos
          </h2>
          <p className="sup-lede">
            Lo que ln2oc da por hecho hoy. Si alguno no se cumple en tu caso, este no es tu servicio, o todavía no.
          </p>
        </div>
        <ol className="sup-list">
          <li className="key">
            <span>
              <b>
                Se consigue mejor ratio de conversión de Lightning a on-chain con cantidades grandes.
              </b>
              {" "}Pasar 5.000.000 sats de una vez cuesta, en porcentaje, bastante menos que pasarlos de a 100.000: quizás 0,2 % o menos, contra el 0,7 % que se cobra por swap chico. Todo el modelo se apoya en esa diferencia (las opciones reales y sus costos están en{" "}
              <a href="/operadores/#h-refill">
                cómo reponer el saldo on-chain
              </a>
              ). Si no se cumpliera, el servicio no cerraría por costo: su valor pasaría a ser la comodidad, y la comisión tendría que reflejarlo (hay usuarios que por comodidad pagarían, por ejemplo, 1 %).
            </span>
          </li>
          <li>
            <span>
              <b>
                Montos chicos.
              </b>
              {" "}Está pensado para quien quiere pasar a on-chain hasta 1.000.000 sats por swap, que es justo donde convertir por su cuenta sale caro.
            </span>
          </li>
          <li>
            <span>
              <b>
                Comisión fija del 0,7 %.
              </b>
              {" "}Es el valor por defecto y cada operador lo puede cambiar. A eso se suma la minería de tu tx.
            </span>
          </li>
          <li>
            <span>
              <b>
                El operador repone el saldo on-chain a mano.
              </b>
              {" "}Junta volumen en Lightning y lo convierte en bloque, o cierra canales. Automatizarlo no es parte de esta versión.
            </span>
          </li>
          <li>
            <span>
              <b>
                Servicio aislado.
              </b>
              {" "}Corre con su propio nodo LN dedicado y su propio dominio, con poca plata adentro. Nunca en un nodo principal ni en uno que se use para otra cosa.
            </span>
          </li>
          <li>
            <span>
              <b>
                Cualquiera puede levantar su instancia.
              </b>
              {" "}El código es GPLv3: con tu nodo, tu dominio y tu comisión.
            </span>
          </li>
          <li>
            <span>
              <b>
                Custodia por segundos, no swap atómico.
              </b>
              {" "}Entre el cobro y la publicación de tu tx, el operador tiene tu plata. Si algo falla ahí, el servicio se frena y te debe el payout.
            </span>
          </li>
        </ol>
      </section>
      <section aria-labelledby="h-moves">
        <h2 id="h-moves">
          El swap en cuatro movimientos
        </h2>
        <ol className="moves">
          <li className="lnstep">
            <b>
              Pedís la invoice
            </b>
            <span>
              Tu wallet LN consulta la Lightning Address y recibe una{" "}
              <em>
                hold invoice
              </em>
              .
            </span>
          </li>
          <li className="lnstep">
            <b>
              Pagás, la plata queda retenida
            </b>
            <span>
              El HTLC llega al nodo y queda trabado. Nadie la cobró todavía.
            </span>
          </li>
          <li className="btcstep">
            <b>
              El nodo chequea saldo y cobra
            </b>
            <span>
              Si tiene sats on-chain para pagarte, liquida la invoice. Si no, la cancela y no perdés nada.
            </span>
          </li>
          <li className="btcstep">
            <b>
              Firma tu tx y la publica
            </b>
            <span>
              Con el pago ya cobrado, firma tu payout, lo guarda y lo publica. Llega a tu cold wallet en el próximo bloque.
            </span>
          </li>
        </ol>
        <p className="read" style={{ color: "var(--muted)" }}>
          Si cuando llega tu pago el nodo no tiene sats on-chain para cubrirlo, la hold invoice se cancela y el pago vuelve a tu wallet. No perdés nada.
        </p>
      </section>
      <section aria-labelledby="h-uses">
        <h2 id="h-uses">
          Para qué sirve
        </h2>
        <div className="uses">
          <div className="use">
            <span className="eyebrow">
              Auto-envío
            </span>
            <h3>
              De tu wallet caliente a frío
            </h3>
            <p>
              Juntaste sats en Wallet of Satoshi, Phoenix o la wallet que uses. Te pagás a tu propia Lightning Address y quedan en tu cold wallet, sin abrir canales ni hacer un swap a mano.
            </p>
          </div>
          <div className="use p2p">
            <span className="eyebrow">
              P2P sin KYC
            </span>
            <h3>
              Cobrás un trade P2P, recibís en frío
            </h3>
            <p>
              Comprás sats en un exchange P2P y, donde te pide cómo cobrar, ponés tu Lightning Address de ln2oc (por ejemplo, en Mostro). Cuando el vendedor libera, los sats van directo a tu cold wallet, sin pasar por una wallet caliente.
            </p>
          </div>
          <div className="use">
            <span className="eyebrow">
              Cobros
            </span>
            <h3>
              Cobrar cualquier cosa
            </h3>
            <p>
              Una venta, una donación, un sueldo en sats: quien te paga usa Lightning y vos recibís on-chain. Para cada cobro podés armar una dirección nueva en segundos.
            </p>
          </div>
        </div>
      </section>
      <section className="isolated" aria-labelledby="h-iso">
        <div>
          <span className="eyebrow">
            Diseño
          </span>
          <h2 id="h-iso" style={{ marginTop: "0.5rem" }}>
            Un servicio aislado, a propósito
          </h2>
        </div>
        <div>
          <p style={{ marginTop: "0" }}>
            ln2oc no es un plugin ni corre adentro de otro programa. Es un servicio aparte, con su propio nodo Lightning y su propio dominio,{" "}
            <b>
              y así es como hay que correrlo
            </b>
            .
          </p>
          <ul className="iso-list">
            <li>
              <b>
                Nodo dedicado.
              </b>
              {" "}Un nodo LND que hace solo esto, con el capital de trabajo de los swaps y nada más.
            </li>
            <li>
              <b>
                Nunca tu nodo principal.
              </b>
              {" "}Ni el de routing, ni uno con mucha plata, ni uno que uses para otra cosa: si algo sale mal, el daño queda acotado a ese nodo.
            </li>
            <li>
              <b>
                Dominio dedicado.
              </b>
              {" "}ln2oc.com existe solo para las Lightning Addresses del servicio.
            </li>
            <li>
              <b>
                Se suma a proyectos Lightning.
              </b>
              {" "}Una wallet, una plataforma P2P o un comercio lo pueden desplegar al lado de su stack, siempre como servicio separado con su nodo propio.
            </li>
          </ul>
        </div>
      </section>
      <section aria-labelledby="h-ch">
        <h2 id="h-ch">
          Capítulos
        </h2>
        <div className="chapters">
          <a className="chapter" href="/usuario/">
            {" "}
            <span className="eyebrow">
              Para quien recibe o se auto-envía
            </span>
            {" "}
            <h3>
              Paso a paso del usuario
            </h3>
            {" "}
            <p>
              Cómo armar tu Lightning Address, qué ves en la wallet en cada momento, cuánto te llega y qué pasa si algo sale mal.
            </p>
            {" "}
            <span className="go">
              /usuario/ →
            </span>
            {" "}
          </a>
          <a className="chapter" href="/operadores/">
            {" "}
            <span className="eyebrow">
              Para vos, que corrés el nodo
            </span>
            {" "}
            <h3>
              Paso a paso del operador
            </h3>
            {" "}
            <p>
              El capital on-chain y la liquidez entrante que necesitás para ser contraparte, cómo se mueve tu balance y cómo operar el servicio.
            </p>
            {" "}
            <span className="go">
              /operadores/ →
            </span>
            {" "}
          </a>
          <a className="chapter" href="/flujo/">
            {" "}
            <span className="eyebrow">
              Animación
            </span>
            {" "}
            <h3>
              El swap en movimiento
            </h3>
            {" "}
            <p>
              La plata y el código, cuadro por cuadro: del HTLC retenido al bloque minado. También el caso sin saldo, con reembolso.
            </p>
            {" "}
            <span className="go">
              /flujo/ →
            </span>
            {" "}
          </a>
          <a className="chapter" href="/arquitectura/">
            {" "}
            <span className="eyebrow">
              Código
            </span>
            {" "}
            <h3>
              Arquitectura
            </h3>
            {" "}
            <p>
              Qué módulo habla con quién, la máquina de estados, los hilos y las reglas que protegen los fondos.
            </p>
            {" "}
            <span className="go">
              /arquitectura/ →
            </span>
            {" "}
          </a>
        </div>
      </section>
      <section className="two" aria-label="Confianza y números">
        <div>
          <h2>
            En qué confiás y en qué no
          </h2>
          <ul className="trust">
            <li className="good">
              <b>
                Que el nodo tenga fondos:
              </b>
              {" "}no hace falta confiar. Si no hay sats on-chain, la hold invoice se cancela y tu pago vuelve.
            </li>
            <li className="good">
              <b>
                Que te paguen dos veces o mal:
              </b>
              {" "}el servicio verifica la tx firmada (destino, monto, inputs) antes de publicarla, y nunca reintenta un pago: ante cualquier duda se frena y lo revisa una persona.
            </li>
            <li className="care">
              <b>
                Los segundos entre el cobro y la publicación:
              </b>
              {" "}el operador ya cobró y todavía tiene que firmar y publicar tu tx. Si algo fallara ahí, el servicio se frena y el operador te debe el payout. No es un swap atómico: es custodia por segundos, no por días.
            </li>
          </ul>
        </div>
        <div>
          <h2>
            Un swap de 100.000 sats
          </h2>
          <SwapLedger />
        </div>
      </section>
    </>
  );
}
