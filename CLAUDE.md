# ln2oc

Servicio de swap **Lightning → on-chain**. La Lightning Address es la dirección on-chain de destino: `<dirección bitcoin>@ln2oc.com`. Te pagan (o te pagás) por Lightning y los sats llegan on-chain a tu cold wallet. Python 3.12, FastAPI, SQLite (SQLAlchemy 2), LND v0.20 por **gRPC**, Docker Compose. Maneja plata real: la seguridad de los fondos manda sobre todo lo demás.

## Cómo trabajar con el usuario

- Hablar en **español rioplatense**. Entender bien antes de tocar código; ante una decisión de diseño que mueva plata, proponer y preguntar.
- **Fail loud**: si algo no está como se espera, frenar (MANUAL_REVIEW / terminar el proceso). Una caída es preferible a perder fondos, del operador o de los usuarios.
- **No atacar casos bordes (filosofía del proyecto)**: a diferencia de otro software, acá cada caso borde manejado es código, y el código es superficie de ataque. Todo lo que no es una regla de negocio (saldo, dust, tasa máxima) va **deliberadamente** a un pánico controlado (`FatalSwapError` → `MANUAL_REVIEW`, el proceso frena). Un caso borde se ataca recién cuando pasa en la realidad. No agregar reintentos, recuperaciones ni ramas "por si acaso"; ante la duda, simplificar.
- Diseños **acotados y secuenciales**: nada cuya concurrencia escale con input del atacante (nada de un hilo por orden). No escuchar el mismo evento por dos caminos a la vez.
- Commitear cuando se termina algo y pushear solo cuando el usuario lo pide. Force push únicamente si lo pide explícitamente.

## Supuestos de negocio (versión actual)

1. **El más importante: se consigue mejor ratio de conversión Lightning → on-chain con cantidades grandes.** Pasar 5.000.000 sats de una vez cuesta, en %, bastante menos que de a 100.000 (CEX ≤ 0,2 % según volumen; cierre cooperativo ~0 %; Loop Out 0,05–0,5 %). El margen es esa diferencia contra la comisión. Si no se cumpliera, el valor sería la comodidad (algunos usuarios pagarían ~1 %).
2. Montos chicos: hasta **1.000.000 sats** por swap (`MAX_SWAP_SAT`).
3. Comisión **0,7 %** por defecto (`SWAP_FEE_RATE`, configurable). La **minería del payout la paga el usuario**, a la tasa del momento de pagar: la estimación de LND + 20 %, y no forma parte del %. Al crear el swap no se estima minería: se guarda `gross_sat` = monto − comisión. El operador gana la comisión más lo cobrado de más en minería (la diferencia siempre va para la casa, nunca en contra).
4. **El operador repone el saldo on-chain a mano** (convertir en bloque, cerrar canales, Loop Out, CEX de paso). Automatizarlo no es parte de esta versión.
5. **Servicio aislado**: nodo LND dedicado y dominio dedicado, con poca plata. Nunca un nodo principal ni uno que se use para otra cosa. Integrable en otros proyectos solo como servicio aparte.
6. Cualquiera puede levantar su propia instancia (GPLv3).
7. No es un swap atómico: custodia por segundos entre el settle y el broadcast.

Casos de uso: auto-envío desde una wallet LN (Wallet of Satoshi, Phoenix…) a cold storage, cobros por LN que llegan on-chain, y cobrar un trade en un exchange P2P (p. ej. Mostro, que paga a Lightning Address; mencionarlo como ejemplo, no como protagonista).

## Flujo de un swap y reglas de fondos

```
PENDING ─(invoice ACCEPTED)─► INVOICE_HOLD ─(settle + tx enviada, en la misma vuelta)─► SUCCESS
   │                              │
   ▼                              ▼
EXPIRED                        FAILED (hold invoice cancelada: el pagador no pierde nada)
MANUAL_REVIEW: todo lo que no es una regla de negocio → el proceso termina y no arranca mientras exista uno.
```

1. `create_swap` (`app/swaps.py`): valida dirección y monto, calcula `gross_sat` = monto − comisión (**sin minería**), **no reserva saldo** (solo un fail-fast contra el saldo gastable menos la reserva) y emite la hold invoice.
2. Polling: invoice `ACCEPTED` → `INVOICE_HOLD`; cancelada → `EXPIRED`; otra cosa → fatal.
3. Cada vuelta (`tick`), si la wallet on-chain tiene **alguna tx sin confirmar** (entrante o saliente, incluido el payout anterior; `GetTransactions`), no se hace nada con los retenidos. Si no, `_pay` toma **todos** los `INVOICE_HOLD` en orden de llegada (cada invoice tiene que seguir `ACCEPTED`; si no, fatal):
   - dirección ya tomada → `FAILED`;
   - se acumula `gross_sat` mientras entre en el saldo gastable menos `ONCHAIN_RESERVE_SAT` (10k: así el cambio nunca queda en dust); desde el primero que no entra, ese y **todos los que siguen** → `FAILED`;
   - minería: `EstimateFee` de la tx con todos los outputs × `MINER_FEE_MARGIN` (1,2), en partes iguales (redondeo hacia arriba). Tasa > `MAX_SAT_PER_VBYTE` → todos `FAILED`; payout bajo dust → ese `FAILED` y se re-estima.
4. En la misma vuelta: settle de cada uno (tiene que quedar `SETTLED` al instante), `FundPsbt` con los payouts netos a la tasa estimada, `FinalizePsbt`, `_verify` (cada destino una vez con su payout, a lo sumo un output más que es el cambio, inputs = UTXOs leaseados, 0 < minería real ≤ lo cobrado), log de la raw tx, `PublishTransaction` y todos a `SUCCESS` en una transacción de la DB (txid, raw tx, `payout_sat`, `actual_fee_sat` = la parte cobrada, `fee_rate_sat_vb`). **Cualquier excepción desde el primer settle → `MANUAL_REVIEW` de todos los swaps de esa tx** ("USER IS OWED"), sin reintentos.

Invariantes (ver `app/worker.py`):
- Un único proceso (lock exclusivo de archivo) y un único hilo worker, que también detecta los pagos (polling síncrono, sin suscripciones); transiciones compare-and-set (`_transition`).
- El payout es un solo paso dentro de una vuelta: no hay estados intermedios que retomar. Una caída a mitad de camino deja un `INVOICE_HOLD` con la invoice `SETTLED` → fatal en la vuelta siguiente (se resuelve a mano).
- Nunca se paga sobre cambio sin confirmar: con cualquier tx de la wallet en el mempool no se paga nada (~1 payout por bloque).
- `LndUnavailable` antes del primer settle → reintento; después → fatal. Excepción: un reembolso primero guarda `FAILED` y después cancela la invoice, así que cualquier falla del cancel → fatal (nadie lo reintentaría).
- TLS hacia LND siempre verificado (falla cerrado).

## Decisiones tomadas (no volver a discutir sin que el usuario lo pida)

- Reservar saldo al emitir la invoice: **descartado** (permitía bloquear liquidez gratis). La liquidez se compromete al recibir el pago.
- Firmar antes del settle o reservar UTXOs con `FundPsbt` antes del settle: **descartado** por el usuario. Con `ACCEPTED` solo se aplican las reglas de negocio.
- REST → **gRPC** con stubs generados desde `proto/` (fijados a LND v0.20.0-beta).
- Minería: **la paga siempre el usuario, a la tasa del momento**: estimación de LND de la tx real + 20 % (`MINER_FEE_MARGIN`), en partes iguales; lo cobrado de más queda para la casa. Sin topes ni reescritura del PSBT (LND no tiene "subtract fee from outputs"). Nada de vbytes hardcodeados.
- **Payouts juntos** (rama `multipayment`): todos los pagos retenidos se pagan en una tx, un output por swap. Estados `PENDING` → `INVOICE_HOLD` → `SUCCESS` (sin `SETTLING`/`PAID`/`SIGNED`/`BROADCASTED`: el payout es atómico dentro de una vuelta). El que no entra en el saldo y **todos los que llegaron después** se reembolsan; misma dirección dos veces → el más nuevo se reembolsa. Sin tope por tx: lo acota `MAX_PENDING_SWAPS` (≤ 1000, para que la tx sea estándar). Sin margen de CLTV: una espera es de ~20 min, no días; si LND cancelara un HTLC, el settle falla → fatal. Que los usuarios de una tx vean los outputs de los demás **no importa** (decisión del usuario). Si da problemas, el plan es **rollback del código** (por eso está en una rama aparte), no un fallback en runtime.
- Detección de pagos: **polling síncrono desde el hilo worker**, `LookupInvoice` de cada `PENDING` de a una, cada `INVOICE_POLL_INTERVAL_SECONDS` (60 s, decidido por el usuario). Tope `MAX_PENDING_SWAPS`. Sin suscripciones. Implementado.
- Sitio web: **lo sirve otro servidor** (nginx de `web/`). FastAPI no sirve archivos del front: solo redirige `GET /` (y HEAD) a `FRONTEND_URL`. El front lee `/api/info`.
- Boltz está caído (desde agosto de 2026); no contarlo como opción de reposición.
- Errores LNURL: **códigos HTTP normales** (400/503/502/500) con `{"status":"ERROR","reason":...}` en el cuerpo, no HTTP 200 (decisión del usuario, aunque LUD-01 diga que el código no importa).
- Lightning Address: **solo direcciones bech32** (`bc1q…`, `bc1p…`) para swaps nuevos; las legacy no, porque LUD-16 exige minúsculas (decisión del usuario).

## Estructura

| Archivo | Rol |
|---|---|
| `app/lnurl.py` | Endpoints LNURL-pay (`/.well-known/lnurlp/{addr}`, `/lnurlp/cb`), handlers sync, `Access-Control-Allow-Origin: *` (LUD-01) |
| `app/swaps.py` | `create_swap` |
| `app/worker.py` | Polling de invoices y payout de los retenidos en una tx; único componente que mueve plata |
| `app/lnd.py` | Cliente gRPC; `LndUnavailable` vs `LndError` |
| `app/tx.py` | Parser estricto de tx (txid, inputs, outputs, vsize) |
| `app/validator.py` | Direcciones → scriptPubKey. Swaps nuevos: **solo bech32 v0 y bech32m v1** (`validate_bitcoin_address`; la Lightning Address va en minúsculas, LUD-16, y base58 distingue mayúsculas). `address_to_script` sigue decodificando base58 para no trabar el payout de un swap ya guardado |
| `app/fees.py` | Tasa de minería (sat/kw → sat/vB) y `calculate_gross` (enteros, basis points). No hay tamaño de tx fijo: la minería sale de la tx real |
| `app/halt.py` | `FatalSwapError` (uno o varios swaps), `halt_process` |
| `app/info.py` | `GET /` → redirect a `FRONTEND_URL`; `GET /api/info` (parámetros de la instancia, commit) |
| `web/` | Sitio estático React + Vite (multi-página), servido por su propio nginx. Ver `web/CLAUDE.md` y README |
| `app/main.py` | Arranque: lock, schema, MANUAL_REVIEW, red de LND, worker |
| `app/config.py` | Settings con validación (falla al arrancar si algo está fuera de rango) |
| `proto/`, `scripts/gen_protos.sh` | Protos de LND vendorizados; stubs en `app/lnrpc/` (no versionado) |
| `scripts/lnaddr_pay.py` | Cliente de prueba: resuelve y valida una Lightning Address como una wallet (LUD-16/06/01) y la paga desde un LND propio |
| `docs/testnet4.md` | Cómo levantar y probar una instancia en testnet4 |
| `docs/prod.md` | Producción: checkout en `/home/lucas/ln2oc/prod/`, datos en `prod/data/` (ignorado), servicio `lnd` del compose |
| `deploy/lnd/mainnet.conf` | LND de prod: mainnet, neutrino, `fee.url`, `tlsextradomain=lnd`, desbloqueo con `wallet_password`, sin REST ni puertos publicados |
| `scripts/lnd/` | Wallet de prod: `init-dirs`, `create-wallet`, `recover-wallet` (24 palabras + passphrase), `backup-scb`, `restore-channels`, `lncli`. Nunca pisan una wallet existente |
| `.env.dev`, `.env.prod` | Muestras de `.env` (regtest/Polar y mainnet). El compose lee `.env` entero (`env_file`); `COMPOSE_PROFILES=lnd` suma el LND |

## Correr y testear

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
PYTHON=.venv/bin/python scripts/gen_protos.sh      # genera app/lnrpc/
.venv/bin/python -m pytest tests -q -p no:cacheprovider   # ~15 s, necesita Polar corriendo (ver tests/CLAUDE.md)
cp .env.dev .env && docker compose up -d --build   # servicios "ln2oc" (API, :8000) y "web" (sitio, :8080); prod: docs/prod.md
cd web && npm ci && npm test && VITE_API_URL=http://127.0.0.1:8000 npm run dev   # sitio en dev (ver web/CLAUDE.md)
```

No hay migraciones: con un cambio de schema, una DB vieja hace que el servicio se niegue a arrancar (`verify_schema`).

## Git

- Remote `origin` = `git@github-freelance:Luquitasjeffrey/ln2oc.git` (alias SSH `github-freelance` en `~/.ssh/config`).
- Se trabaja **directo en `main`** (pedido del usuario). `fix/safe-payout-flow` ya está mergeada (fast-forward) en `main`. `master` es la rama local vieja.
- **Commits firmados con GPG** (`commit.gpgsign=true`, la llave del usuario). `--no-gpg-sign` solo si el usuario lo autoriza para esa sesión, y antes de pushear hay que volver a firmar los commits no pusheados: `git rebase --force-rebase --gpg-sign origin/main` (cambian los hashes; actualizar si están citados en la memoria). Hay commits viejos sin firma ya pusheados: no reescribirlos sin pedido explícito (sería force push).

## Artifact de documentación

Artifact maestro "ln2oc": https://claude.ai/artifact/6LgQxcXLa1o3efcnLxiFkx (páginas: índice con supuestos, usuario, operador, animación `flujo.html`, arquitectura). Para editarlo en otra sesión: leerlo con la acción `read`/`read_file` del Artifact tool y republicar con su `url` (las fuentes locales estaban en el scratchpad de la sesión anterior y pueden no existir). El sitio `web/` porta este contenido (páginas en `web/src/pages/`, animación en `web/src/flujo/animation.js`): si cambia el flujo, actualizar ambos. Si el código cambia el flujo, actualizar la animación "por dentro" y la máquina de estados de `arquitectura.html`.

## TODO priorizado

**Decidido y sin implementar**
3. Macaroon con permisos mínimos (diferido por el usuario).

**El artifact lo promete y el código no lo cumple del todo**
4. **`description_hash` en la hold invoice: ya no es obligatorio.** LUD-06 sacó el requisito (lnurl/luds PR #234, mergeado en mayo de 2026). Phoenix y BlueWallet no lo exigen; ZEUS solo rechaza si la invoice trae un `h` que no coincide, y una invoice sin `h` la acepta. Hoy mandamos `memo` sin `h`. Agregarlo (sha256 de la metadata exacta, en `AddHoldInvoice.description_hash`) solo ayudaría con wallets viejas. Baja prioridad; confirmarlo en la prueba de testnet4 (9).
5. **`minSendable` dinámico** según el fee del momento (hoy fijo en `MIN_SWAP_SAT`; un monto que no cubre minería + dust recién se detecta con el pago retenido y se reembolsa).

**Antes de mainnet**
6. Alertas activas (halt, MANUAL_REVIEW, LND sin responder).
7. Backup continuo de la SQLite (preimages, raw tx) y SCB de LND.
8. Tope de payouts por hora/día y kill switch manual.
9. Prueba en testnet4 con wallets reales. Preparada: `BITCOIN_NETWORK=testnet4`, guía en `docs/testnet4.md`, `.env.testnet4.example` y `scripts/lnaddr_pay.py` (paga una Lightning Address como una wallet, contra el dominio real). Falta: nodos, dominio con HTTPS y la prueba en sí. No se confirmó ninguna wallet móvil que pague Lightning Address en testnet4 (candidata: ZEUS remoto contra el LND pagador). Signet no está soportado.

**Operativo**
10. Nodo (hecho: servicio `lnd` del compose, ver `docs/prod.md`; falta crear la wallet y fondearlo) y dominio dedicados, HTTPS con reverse proxy, `DOMAIN=ln2oc.com`, `EXTERNAL_URL=https://ln2oc.com`.
11. Aviso cuando el saldo on-chain gastable baja de un umbral (la reposición en sí es manual).

**Para charlar**
12. Seguimiento de confirmaciones (`SUCCESS` es terminal; una tx trabada no se detecta).
13. `/healthz` real (worker vivo, LND accesible y sincronizado).
14. **Wallet con una tx que nunca confirma frena todos los payouts** (baja prioridad: al atacante le cuesta plata y no gana nada). Ataque: mandar una tx chica a nuestra dirección de cambio (visible en cualquier payout) y reemplazarla por RBF; btcwallet puede seguir mostrándola sin confirmar para siempre. Lo mismo pasa sin atacante si nuestro payout se traba por una suba de minería. Efecto: los pagos quedan retenidos hasta que LND cancela los HTLC cerca de su vencimiento, y eso es fatal (`MANUAL_REVIEW`); mientras tanto los HTLC traban canales. No se pierden fondos. Opciones: frenar solo por txs que gastan UTXOs propios (`previous_outpoints[].is_our_output`; los depósitos sin confirmar no afectan con `ONCHAIN_MIN_CONFS=1`), 503 en `create_swap` cuando el worker lleva X min frenado, tope de espera menor que el CLTV, alerta (6). Remedio manual: `lncli wallet removetx`.

Orden propuesto: 9 (testnet4) → 5 → 6, 11 → 7, 8; el 4 según lo que muestre la prueba. (Hechos y pusheados: el 1, polling síncrono, y el 2, sitio React en `web/` con `/api/info`.)
