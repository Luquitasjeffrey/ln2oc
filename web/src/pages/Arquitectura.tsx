export default function Arquitectura() {
  return (
    <>
      <header className="hero read">
        <div className="eyebrow">
          Código
        </div>
        <h1 style={{ marginTop: "0.9rem" }}>
          Arquitectura de ln2oc
        </h1>
        <p className="lede">
          Un proceso, una base SQLite y un nodo LND dedicado, por gRPC. El API solo emite invoices; un único worker mueve la plata, y nada más en el sistema puede hacerlo. Todo el conjunto es un servicio aislado: su propio nodo, su propio dominio.
        </p>
      </header>
      <section aria-labelledby="h-comp">
        <h2 id="h-comp" className="read">
          Quién habla con quién
        </h2>
        <figure>
          <div className="canvas">
            <svg className="dg wide" viewBox="0 0 1120 590" role="img" aria-label="El pagador llama al API LNURL, que crea el swap y la hold invoice; el pago viaja por Lightning hasta LND; el worker consulta las invoices pendientes en LND, que fondea, firma, liquida y publica vía LND; la tx publicada llega por la red Bitcoin a la cold wallet del usuario.">
              <defs>
                <marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="hd" />
                </marker>
                <marker id="a-ln" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="hd-ln" />
                </marker>
                <marker id="a-btc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="hd-btc" />
                </marker>
              </defs>
              <rect x="200" y="56" width="530" height="456" rx="12" className="boundary" />
              <text x="214" y="78" className="m mut">
                proceso único · lock exclusivo de archivo
              </text>
              <rect x="20" y="100" width="150" height="60" rx="8" className="box" />
              <text x="95" y="126" textAnchor="middle" className="t">
                Wallet LN
              </text>
              <text x="95" y="145" textAnchor="middle" className="mut">
                del pagador
              </text>
              <rect x="230" y="100" width="200" height="60" rx="8" className="box" />
              <text x="330" y="125" textAnchor="middle" className="t">
                lnurl.py
              </text>
              <text x="330" y="145" textAnchor="middle" className="m mut">
                FastAPI · handlers sync
              </text>
              <path d="M170 130 L224 130" className="e" markerEnd="url(#a)" />
              <text x="197" y="120" textAnchor="middle" className="m mut">
                HTTPS
              </text>
              <rect x="230" y="200" width="200" height="60" rx="8" className="box" />
              <text x="330" y="225" textAnchor="middle" className="t">
                swaps.py
              </text>
              <text x="330" y="245" textAnchor="middle" className="m mut">
                create_swap · no reserva saldo
              </text>
              <path d="M330 160 L330 194" className="e" markerEnd="url(#a)" />
              <text x="330" y="292" textAnchor="middle" className="m mut">
                helpers del worker
              </text>
              <rect x="230" y="302" width="94" height="40" rx="6" className="box" />
              <text x="277" y="327" textAnchor="middle" className="m">
                tx.py
              </text>
              <rect x="336" y="302" width="94" height="40" rx="6" className="box" />
              <text x="383" y="327" textAnchor="middle" className="m">
                validator.py
              </text>
              <rect x="230" y="352" width="94" height="40" rx="6" className="box" />
              <text x="277" y="377" textAnchor="middle" className="m">
                fees.py
              </text>
              <rect x="336" y="352" width="94" height="40" rx="6" className="box" />
              <text x="383" y="377" textAnchor="middle" className="m">
                halt.py
              </text>
              <rect x="470" y="100" width="230" height="292" rx="8" className="core" />
              <text x="585" y="128" textAnchor="middle" className="t">
                worker.py
              </text>
              <text x="585" y="150" textAnchor="middle" className="m mut">
                1 hilo · máquina de estados
              </text>
              <text x="585" y="168" textAnchor="middle" className="m mut">
                1 payout por vuelta
              </text>
              <text x="585" y="186" textAnchor="middle" className="m mut">
                único que mueve plata
              </text>
              <rect x="486" y="300" width="198" height="78" rx="6" className="box" />
              <text x="585" y="322" textAnchor="middle" className="t">
                Detección de pagos
              </text>
              <text x="585" y="342" textAnchor="middle" className="m mut">
                LookupInvoice de cada PENDING
              </text>
              <text x="585" y="362" textAnchor="middle" className="m mut">
                mismo hilo · cada 60 s
              </text>
              <rect x="230" y="436" width="470" height="56" rx="8" className="box" />
              <text x="465" y="460" textAnchor="middle" className="t">
                SQLite · models.py
              </text>
              <text x="465" y="479" textAnchor="middle" className="m mut">
                swaps: estado, preimage, raw_tx, txid
              </text>
              <path d="M230 240 C 206 280, 206 410, 262 436" className="e" markerEnd="url(#a)" />
              <text x="196" y="330" textAnchor="end" className="m mut">
                INSERT
              </text>
              <text x="196" y="345" textAnchor="end" className="m mut">
                PENDING
              </text>
              <path d="M640 392 L640 430" className="e" markerEnd="url(#a)" />
              <text x="648" y="416" className="m mut">
                transiciones CAS
              </text>
              <rect x="790" y="56" width="310" height="370" rx="12" className="lnd" />
              <text x="945" y="82" textAnchor="middle" className="t">
                LND dedicado · v0.20 · gRPC
              </text>
              <rect x="806" y="98" width="278" height="92" rx="8" className="box" />
              <text x="822" y="120" className="t lnt">
                Invoices
              </text>
              <text x="822" y="140" className="m mut">
                AddHoldInvoice · LookupInvoiceV2
              </text>
              <text x="822" y="157" className="m mut">
                SettleInvoice · CancelInvoice
              </text>
              <text x="822" y="174" className="m mut">
                sin suscripciones (polling)
              </text>
              <rect x="806" y="204" width="278" height="112" rx="8" className="box" />
              <text x="822" y="226" className="t btct">
                WalletKit
              </text>
              <text x="822" y="246" className="m mut">
                EstimateFee
              </text>
              <text x="822" y="263" className="m mut">
                FundPsbt · FinalizePsbt
              </text>
              <text x="822" y="280" className="m mut">
                PublishTransaction
              </text>
              <text x="822" y="297" className="m mut">
                ListLeases · ReleaseOutput
              </text>
              <rect x="806" y="330" width="278" height="76" rx="8" className="box" />
              <text x="822" y="352" className="t">
                Lightning
              </text>
              <text x="822" y="372" className="m mut">
                GetInfo · WalletBalance · EstimateFee
              </text>
              <text x="822" y="389" className="m mut">
                (red, altura, sync, saldo, simulación)
              </text>
              <path d="M430 230 L450 230 L450 90 L770 90 L770 110 L800 110" className="e" markerEnd="url(#a)" />
              <text x="610" y="84" textAnchor="middle" className="m mut">
                AddHoldInvoice
              </text>
              <path d="M700 150 L800 150" className="e" markerEnd="url(#a)" markerStart="url(#a)" />
              <text x="750" y="142" textAnchor="middle" className="m mut">
                estado
              </text>
              <text x="750" y="168" textAnchor="middle" className="m mut">
                settle · cancel
              </text>
              <path d="M700 262 L800 262" className="e" markerEnd="url(#a)" markerStart="url(#a)" />
              <text x="750" y="254" textAnchor="middle" className="m mut">
                fondea · firma
              </text>
              <text x="750" y="280" textAnchor="middle" className="m mut">
                publica
              </text>
              <path d="M700 368 L800 368" className="e" markerEnd="url(#a)" />
              <text x="750" y="360" textAnchor="middle" className="m mut">
                altura · sync
              </text>
              <path d="M95 100 L95 30 L945 30 L945 56" className="e-ln" markerEnd="url(#a-ln)" />
              <text x="520" y="22" textAnchor="middle" className="m lnt">
                el HTLC viaja por la red Lightning hasta tu nodo
              </text>
              <rect x="806" y="470" width="278" height="56" rx="8" className="box" />
              <text x="945" y="494" textAnchor="middle" className="t btct">
                Red Bitcoin
              </text>
              <text x="945" y="513" textAnchor="middle" className="m mut">
                mempool → bloque
              </text>
              <path d="M945 426 L945 464" className="e-btc" markerEnd="url(#a-btc)" />
              <text x="954" y="450" className="m btct">
                tx publicada
              </text>
              <rect x="20" y="520" width="150" height="56" rx="8" className="box" />
              <text x="95" y="545" textAnchor="middle" className="t">
                Cold wallet
              </text>
              <text x="95" y="564" textAnchor="middle" className="mut">
                del usuario
              </text>
              <path d="M806 548 L176 548" className="e-btc" markerEnd="url(#a-btc)" />
              <text x="490" y="540" textAnchor="middle" className="m btct">
                payout on-chain
              </text>
            </svg>
          </div>
          <figcaption>
            El API solo crea swaps{" "}
            <code>
              PENDING
            </code>
            {" "}y su hold invoice. Todo lo que mueve sats (fondear, firmar, liquidar, publicar, cancelar) lo hace el worker, en un solo hilo y con transiciones compare-and-set sobre la DB. La detección de pagos vive dentro del worker: cada minuto (configurable) consulta con LookupInvoice cada invoice pendiente, de a una, en el mismo hilo. No hay suscripciones ni un hilo por invoice, y la cantidad de swaps pendientes tiene un tope.
          </figcaption>
        </figure>
      </section>
      <section aria-labelledby="h-sm">
        <h2 id="h-sm" className="read">
          La máquina de estados
        </h2>
        <p className="read">
          Cada swap vive en un estado guardado en la DB. El pago on-chain es un solo paso dentro de una vuelta del worker: no hay estados intermedios que retomar. Si algo se corta a mitad de camino, el servicio se frena y lo revisa una persona.
        </p>
        <figure>
          <div className="canvas">
            <svg className="dg wide" viewBox="0 0 1150 340" role="img" aria-label="Máquina de estados: PENDING, INVOICE_HOLD, SUCCESS. En INVOICE_HOLD se espera a que la wallet no tenga tx sin confirmar y se aplican las reglas de saldo y dust; lo que no entra va a FAILED. Desde el settle, cualquier falla va a MANUAL_REVIEW.">
              <defs>
                <marker id="s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="hd" />
                </marker>
              </defs>
              <line x1="560" y1="20" x2="560" y2="330" className="noreturn" />
              <text x="572" y="34" className="m btct">
                desde el settle el operador ya cobró:
              </text>
              <text x="572" y="50" className="m btct">
                no hay reembolso ni reintentos
              </text>
              <rect x="20" y="70" width="130" height="44" rx="22" className="st" />
              <text x="85" y="97" textAnchor="middle" className="m" style={{ fontWeight: "600" }}>
                PENDING
              </text>
              <rect x="300" y="70" width="170" height="44" rx="22" className="st" />
              <text x="385" y="97" textAnchor="middle" className="m" style={{ fontWeight: "600" }}>
                INVOICE_HOLD
              </text>
              <rect x="900" y="70" width="170" height="44" rx="22" className="st-ok" />
              <text x="985" y="97" textAnchor="middle" className="m okt" style={{ fontWeight: "600" }}>
                SUCCESS
              </text>
              <path d="M150 92 L294 92" className="e" markerEnd="url(#s)" />
              <text x="222" y="134" textAnchor="middle" className="m mut">
                invoice
              </text>
              <text x="222" y="149" textAnchor="middle" className="m mut">
                ACCEPTED
              </text>
              <path d="M470 92 L894 92" className="e" markerEnd="url(#s)" />
              <text x="515" y="134" textAnchor="middle" className="m mut">
                wallet quieta,
              </text>
              <text x="515" y="149" textAnchor="middle" className="m mut">
                saldo OK
              </text>
              <text x="730" y="134" textAnchor="middle" className="m mut">
                settle + fondear + firmar
              </text>
              <text x="730" y="149" textAnchor="middle" className="m mut">
                + verificar + publicar
              </text>
              <rect x="20" y="236" width="130" height="44" rx="22" className="st" />
              <text x="85" y="263" textAnchor="middle" className="m" style={{ fontWeight: "600" }}>
                EXPIRED
              </text>
              <rect x="320" y="236" width="130" height="44" rx="22" className="st-bad" />
              <text x="385" y="263" textAnchor="middle" className="m badt" style={{ fontWeight: "600" }}>
                FAILED
              </text>
              <path d="M85 114 L85 230" className="e" markerEnd="url(#s)" />
              <text x="94" y="176" className="m mut">
                no pagada
              </text>
              <path d="M385 114 L385 230" className="e" markerEnd="url(#s)" />
              <text x="393" y="164" className="m mut">
                sin saldo, dust
              </text>
              <text x="393" y="179" className="m mut">
                o dirección repetida:
              </text>
              <text x="393" y="194" className="m mut">
                CancelInvoice
              </text>
              <rect x="760" y="226" width="370" height="64" rx="10" className="st-bad" />
              <text x="945" y="252" textAnchor="middle" className="m badt" style={{ fontWeight: "600" }}>
                MANUAL_REVIEW
              </text>
              <text x="945" y="272" textAnchor="middle" className="m mut">
                cualquier cosa fuera de las reglas:
              </text>
              <text x="945" y="287" textAnchor="middle" className="m mut">
                frena el proceso y no arranca más
              </text>
            </svg>
          </div>
          <figcaption>
            A la izquierda de la línea punteada, la invoice está en{" "}
            <code>
              ACCEPTED
            </code>
            : mientras la wallet on-chain tenga alguna tx sin confirmar no se hace nada. Con la wallet quieta, todos los pagos retenidos se pagan en una sola tx, del más viejo al más nuevo: desde el primero que no entra en el saldo (menos una reserva que nunca se paga, para que el cambio no quede en dust), ese y todos los que siguen se cancelan, igual que una dirección repetida o un payout que la minería dejaría en dust. Si LND no puede leer el saldo o estimar la tx, el servicio se frena. A la derecha, en la misma vuelta: settle, fondeo, firma, verificación y publicación. Cualquier falla en ese tramo frena el servicio, sin reintentos.
          </figcaption>
        </figure>
      </section>
      <section className="read" aria-labelledby="h-rules">
        <h2 id="h-rules">
          Las reglas que protegen los fondos
        </h2>
        <ol className="rules">
          <li>
            <span>
              <b>
                La tx on-chain se arma recién con la invoice{" "}
                <code>
                  SETTLED
                </code>
                .
              </b>
              {" "}Con la invoice en{" "}
              <code>
                ACCEPTED
              </code>
              {" "}lo único que se hace es esperar a que no quede ninguna tx de la wallet en la mempool y aplicar las reglas: saldo (menos la reserva), dust y tasa máxima.
            </span>
          </li>
          <li>
            <span>
              <b>
                La minería la pagan los usuarios, con margen.
              </b>
              {" "}Es la estimación del nodo para la tx real, a la tasa del momento, más un 20 %, en partes iguales. Antes de publicar se verifica que la minería real no supere lo cobrado.
            </span>
          </li>
          <li>
            <span>
              <b>
                Sin saldo, se cancela la hold invoice antes de cobrar.
              </b>
              {" "}Los sats del pagador nunca salen de su wallet.
            </span>
          </li>
          <li>
            <span>
              <b>
                No se atajan casos bordes.
              </b>
              {" "}Cada caso borde manejado es código, y el código es superficie de ataque. Lo que no es una regla de negocio frena el servicio a propósito; se ataca recién cuando pasa.
            </span>
          </li>
          <li>
            <span>
              <b>
                Si algo no es como se espera, el servicio se frena.
              </b>
              {" "}El swap queda en{" "}
              <code>
                MANUAL_REVIEW
              </code>
              {" "}y el proceso no vuelve a arrancar hasta que alguien lo revise. Una caída es preferible a una pérdida.
            </span>
          </li>
        </ol>
      </section>
      <section aria-labelledby="h-mods">
        <h2 id="h-mods" className="read">
          Los módulos
        </h2>
        <div className="table-wrap">
          <table className="ledger mods">
            <thead>
              <tr>
                <th>
                  Archivo
                </th>
                <th>
                  Qué hace
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  app/lnurl.py
                </td>
                <td>
                  Endpoints LNURL-pay. Validan dirección y monto, y devuelven la hold invoice.
                </td>
              </tr>
              <tr>
                <td>
                  app/swaps.py
                </td>
                <td>
                  Crea el swap: calcula monto − comisión (sin minería: se fija al pagar), emite la hold invoice y guarda el swap{" "}
                  <code>
                    PENDING
                  </code>
                  . No reserva saldo para el swap: el compromiso se toma al llegar el pago.
                </td>
              </tr>
              <tr>
                <td>
                  app/worker.py
                </td>
                <td>
                  Único hilo que mueve plata: paga todos los pagos retenidos en una tx (un output por swap), en un solo paso, con transiciones compare-and-set. También detecta los pagos: cada INVOICE_POLL_INTERVAL_SECONDS consulta cada swap PENDING con LookupInvoice, de a uno.
                </td>
              </tr>
              <tr>
                <td>
                  app/lnd.py
                </td>
                <td>
                  Cliente gRPC de LND. Separa los errores en{" "}
                  <em>
                    ambiguos
                  </em>
                  {" "}(puede haberse ejecutado) y{" "}
                  <em>
                    definitivos
                  </em>
                  {" "}(LND lo rechazó). TLS verificado siempre.
                </td>
              </tr>
              <tr>
                <td>
                  app/tx.py
                </td>
                <td>
                  Parser estricto de transacciones: recalcula el txid y lee inputs y outputs para verificar lo que firmó LND.
                </td>
              </tr>
              <tr>
                <td>
                  app/validator.py
                </td>
                <td>
                  Valida direcciones por red y las convierte a scriptPubKey. Para un swap nuevo acepta solo Bech32 (SegWit v0) y Bech32m (Taproot): una Lightning Address va en minúsculas y Base58Check distingue mayúsculas.
                </td>
              </tr>
              <tr>
                <td>
                  app/fees.py
                </td>
                <td>
                  Tasa de minería (sat/kw → sat/vB, redondeando para arriba) y monto − comisión con aritmética entera. La minería de cada payout es la estimación de LND para la tx real, + 20 %; la tx se fondea con esa misma tasa de LND, sin redondearla.
                </td>
              </tr>
              <tr>
                <td>
                  app/halt.py
                </td>
                <td>
                  Fail loud: marca{" "}
                  <code>
                    MANUAL_REVIEW
                  </code>
                  {" "}y termina el proceso.
                </td>
              </tr>
              <tr>
                <td>
                  app/main.py
                </td>
                <td>
                  Arranque: lock de proceso, schema, chequeo de red de LND, swaps en revisión, y start del worker.
                </td>
              </tr>
              <tr>
                <td>
                  proto/ · scripts/gen_protos.sh
                </td>
                <td>
                  Protos de LND v0.20.0-beta vendorizados; los stubs se generan en el build.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <div className="pager">
        <a href="/flujo/">
          ← El swap en movimiento
        </a>
        <a href="/">
          ln2oc →
        </a>
      </div>
    </>
  );
}
