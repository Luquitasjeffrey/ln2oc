# ln2oc

Servicio de swap **Lightning → on-chain**. La Lightning Address es la dirección on-chain de destino: `<dirección bitcoin>@ln2oc.com`. Te pagan (o te pagás) por Lightning y los sats llegan on-chain a tu cold wallet. Python 3.12, FastAPI, SQLite (SQLAlchemy 2), LND v0.20 por **gRPC**, Docker Compose. Maneja plata real: la seguridad de los fondos manda sobre todo lo demás.

## Cómo trabajar con el usuario

- Hablar en **español rioplatense**. Entender bien antes de tocar código; ante una decisión de diseño que mueva plata, proponer y preguntar.
- **Fail loud**: si algo no está como se espera, frenar (MANUAL_REVIEW / terminar el proceso). Una caída es preferible a perder fondos, del operador o de los usuarios.
- Diseños **acotados y secuenciales**: nada cuya concurrencia escale con input del atacante (nada de un hilo por orden). No escuchar el mismo evento por dos caminos a la vez.
- Commitear cuando se termina algo y pushear solo cuando el usuario lo pide. Force push únicamente si lo pide explícitamente.

## Supuestos de negocio (versión actual)

1. **El más importante: se consigue mejor ratio de conversión Lightning → on-chain con cantidades grandes.** Pasar 5.000.000 sats de una vez cuesta, en %, bastante menos que de a 100.000 (CEX ≤ 0,2 % según volumen; cierre cooperativo ~0 %; Loop Out 0,05–0,5 %). El margen es esa diferencia contra la comisión. Si no se cumpliera, el valor sería la comodidad (algunos usuarios pagarían ~1 %).
2. Montos chicos: hasta **1.000.000 sats** por swap (`MAX_SWAP_SAT`).
3. Comisión **0,7 %** por defecto (`SWAP_FEE_RATE`, configurable). La **minería del payout la paga el usuario** (`miner_fee_sat`, 160 vB × sat/vB cotizado) y no forma parte del %.
4. **El operador repone el saldo on-chain a mano** (convertir en bloque, cerrar canales, Loop Out, CEX de paso). Automatizarlo no es parte de esta versión.
5. **Servicio aislado**: nodo LND dedicado y dominio dedicado, con poca plata. Nunca un nodo principal ni uno que se use para otra cosa. Integrable en otros proyectos solo como servicio aparte.
6. Cualquiera puede levantar su propia instancia (GPLv3).
7. No es un swap atómico: custodia por segundos entre el settle y el broadcast.

Casos de uso: auto-envío desde una wallet LN (Wallet of Satoshi, Phoenix…) a cold storage, cobros por LN que llegan on-chain, y cobrar un trade en un exchange P2P (p. ej. Mostro, que paga a Lightning Address; mencionarlo como ejemplo, no como protagonista).

## Flujo de un swap y reglas de fondos

```
PENDING ─(invoice ACCEPTED)─► SETTLING ─(invoice SETTLED)─► PAID ─(tx firmada y guardada)─► SIGNED ─(broadcast)─► BROADCASTED
   │                             │ solo chequea saldo + margen CLTV
   ▼                             ▼
EXPIRED                      CANCELING ─► FAILED (hold invoice cancelada: el pagador no pierde nada)
MANUAL_REVIEW: invariante roto → el proceso termina y no arranca mientras exista uno.
```

1. `create_swap` (`app/swaps.py`): valida dirección y monto, estima fee (sin estimación → rechaza), **no reserva saldo** (solo un fail-fast contra el saldo gastable), guarda la tasa cotizada (`fee_rate_sat_vb`) y emite la hold invoice.
2. Invoice `ACCEPTED` → `SETTLING`: **lo único que se hace es chequear saldo** on-chain (`WalletBalance`, confirmado − reserva de anchors ≥ payout + minería) y el margen de CLTV (`MIN_CLTV_MARGIN_BLOCKS`). Si no alcanza → cancelar la hold invoice. **No se fondea ni se firma nada.**
3. Settle y esperar a que LND reporte `SETTLED` → `PAID`. Desde acá se le debe el payout al usuario: cualquier falla posterior va a `MANUAL_REVIEW` ("USER IS OWED"), nunca a un reembolso automático.
4. `PAID` → `SIGNED`: `FundPsbt` (a la tasa cotizada) + `FinalizePsbt`, verificación independiente de la tx (`app/tx.py`: destino, monto, inputs = UTXOs leaseados) y **raw tx + txid guardados en la DB antes del broadcast**.
5. `SIGNED` → `BROADCASTED`: publicar la tx guardada. Reintentar es idempotente.

Invariantes (ver `app/worker.py`):
- Un único proceso (lock exclusivo de archivo) y un único hilo worker; transiciones compare-and-set (`_transition`).
- Como máximo **un payout en vuelo** (`SETTLING`/`PAID`/`SIGNED`) para que el chequeo de saldo del siguiente vea la wallet ya gastada.
- Resultado ambiguo de LND (`LndUnavailable`: timeout, conexión cortada) nunca se toma como fracaso: se vuelve a consultar el estado. `LndError` = LND rechazó explícitamente.
- TLS hacia LND siempre verificado (falla cerrado).

## Decisiones tomadas (no volver a discutir sin que el usuario lo pida)

- Reservar saldo al emitir la invoice: **descartado** (permitía bloquear liquidez gratis). La liquidez se compromete al recibir el pago.
- Firmar antes del settle o reservar UTXOs con `FundPsbt` antes del settle: **descartado** por el usuario. Con `ACCEPTED` solo se mira el saldo.
- REST → **gRPC** con stubs generados desde `proto/` (fijados a LND v0.20.0-beta).
- Detección de pagos: **un solo job síncrono que consulta todas las invoices pendientes, de a una** (reemplaza a `app/invoice_watcher.py`). Sin barrido + suscripción a la vez.
- Boltz está caído (desde agosto de 2026); no contarlo como opción de reposición.

## Estructura

| Archivo | Rol |
|---|---|
| `app/lnurl.py` | Endpoints LNURL-pay (`/.well-known/lnurlp/{addr}`, `/lnurlp/cb`), handlers sync |
| `app/swaps.py` | `create_swap` |
| `app/worker.py` | Máquina de estados; único componente que mueve plata |
| `app/invoice_watcher.py` | **A reemplazar**: hoy una suscripción `SubscribeSingleInvoice` por invoice, en un hilo cada una |
| `app/lnd.py` | Cliente gRPC; `LndUnavailable` vs `LndError` |
| `app/tx.py` | Parser estricto de tx (txid, inputs, outputs) |
| `app/validator.py` | Direcciones bech32/bech32m/base58 → scriptPubKey |
| `app/fees.py` | Estimación de fee y cálculo de payout (enteros, basis points) |
| `app/halt.py` | `FatalSwapError`, `halt_process` |
| `app/main.py` | Arranque: lock, schema, MANUAL_REVIEW, red de LND, worker |
| `app/config.py` | Settings con validación (falla al arrancar si algo está fuera de rango) |
| `proto/`, `scripts/gen_protos.sh` | Protos de LND vendorizados; stubs en `app/lnrpc/` (no versionado) |

## Correr y testear

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
PYTHON=.venv/bin/python scripts/gen_protos.sh      # genera app/lnrpc/
.venv/bin/python -m pytest tests -q -p no:cacheprovider   # ~15 s, necesita Polar corriendo (ver tests/CLAUDE.md)
docker compose up -d --build                        # servicio "ln2oc", volumen ln2oc_data
```

No hay migraciones: con un cambio de schema, una DB vieja hace que el servicio se niegue a arrancar (`verify_schema`).

## Git

- Remote `origin` = `git@github-freelance:Luquitasjeffrey/ln2oc.git` (alias SSH `github-freelance` en `~/.ssh/config`).
- `main` = código original + LICENSE (GPLv3). El trabajo actual está en **`fix/safe-payout-flow`** (pusheada), todavía sin PR a `main`. `master` es la rama local vieja.

## Artifact de documentación

Artifact maestro "ln2oc": https://claude.ai/artifact/6LgQxcXLa1o3efcnLxiFkx (páginas: índice con supuestos, usuario, operador, animación `flujo.html`, arquitectura). Para editarlo en otra sesión: leerlo con la acción `read`/`read_file` del Artifact tool y republicar con su `url` (las fuentes locales estaban en el scratchpad de la sesión anterior y pueden no existir). Si el código cambia el flujo, actualizar la animación "por dentro" y la máquina de estados de `arquitectura.html`.

## TODO priorizado

**Decidido y sin implementar**
1. **Polling síncrono de invoices** en lugar de `invoice_watcher.py`: un job, de a una invoice. **Pendiente decidir el intervalo**: el usuario dijo ~1 minuto; propuesta 10–15 s porque exchanges P2P como Mostro esperan hasta 60 s por pago y reintentan. Actualizar tests de suscripción, README y artifact.
2. Atajo "pegá tu dirección → `@ln2oc.com`": hoy solo existe en el artifact (`addr.js`, validación en el navegador). Si va al producto: landing en `/`.
3. Macaroon con permisos mínimos (diferido por el usuario).

**El artifact lo promete y el código no lo cumple del todo**
4. **`description_hash` = sha256(metadata) en la hold invoice (LUD-06).** Sin eso muchas wallets rechazan la invoice. Es el mayor riesgo de que no funcione en la práctica.
5. **`minSendable` dinámico** según el fee del momento (hoy fijo en 1.000 sats y el callback rechaza montos que no cubren minería + dust).

**Antes de mainnet**
6. Alertas activas (halt, MANUAL_REVIEW, LND sin responder).
7. Backup continuo de la SQLite (preimages, raw tx) y SCB de LND.
8. Tope de payouts por hora/día y kill switch manual.
9. Prueba en testnet/signet con wallets reales (signet no está soportado hoy).

**Operativo**
10. Nodo y dominio dedicados, HTTPS con reverse proxy, `DOMAIN=ln2oc.com`, `EXTERNAL_URL=https://ln2oc.com`.
11. Aviso cuando el saldo on-chain gastable baja de un umbral (la reposición en sí es manual).

**Para charlar**
12. Seguimiento de confirmaciones (`BROADCASTED` es terminal; una tx trabada no se detecta).
13. `/healthz` real (worker vivo, LND accesible y sincronizado).

Orden propuesto: 1 → 4, 5 → 6, 11 → 7, 8, 9.
