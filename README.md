# ln2oc ⚡ ➔ ₿

Servicio minimalista y confiable de **Lightning → Bitcoin On-chain Swap-out** implementado en Python 3.12+ con FastAPI, SQLite (SQLAlchemy 2.x), la API gRPC de LND y Docker Compose.

---

## 📖 ¿Cómo funciona?

El servicio expone un endpoint estándar de **Lightning Address (LNURL-Pay)** donde el "usuario" es la dirección de destino on-chain:

```text
<DIRECCION_BITCOIN>@tudominio.com
```

Por ejemplo:
- Regtest: `bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz@127.0.0.1:8000`
- Mainnet: `bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr@ln2oc.com`

### Flujo de Ejecución

Criterios de diseño, en orden de prioridad:
1. **No se paga on-chain hasta que el pago Lightning está cobrado** (invoice `SETTLED`).
2. **Si no hay saldo on-chain cuando llega el pago, se cancela la hold invoice** y el pagador recupera su plata.
3. **Fail loud**: si algo no está como se espera, el swap queda en `MANUAL_REVIEW` y el proceso se detiene. Es preferible una caída del servicio a una pérdida de fondos.

```text
PENDING ──(hold invoice ACCEPTED)──► FUNDING ──(tx firmada y guardada)──► SIGNED ──(settle LN)──► PAID ──(publicar)──► BROADCASTED
   │                                    └──────────────► CANCELING ◄─────────┘
   ▼                                                          ▼
EXPIRED (nunca se pagó)                               FAILED (invoice cancelada, pagador reembolsado)
```

1. **LNURL-Pay**: valida la dirección y el monto, y estima el fee on-chain (si no hay estimación, rechaza). **No reserva saldo**: si el saldo gastable ya no alcanza, rechaza de entrada, pero las invoices sin pagar no bloquean liquidez. La liquidez se compromete recién cuando llega el pago (paso 4) y, si en ese momento no hay fondos, se cancela la hold invoice.
   $$\text{payout} = \lfloor \text{amount\_sat} \times (1 - \text{SWAP\_FEE\_RATE}) \rfloor - \text{miner\_fee\_sat}$$
2. **Hold invoice** (`AddHoldInvoice`) con `cltv_expiry` explícito.
3. **Pago retenido (`ACCEPTED`)**: el worker verifica el monto pagado y que el HTLC tenga un margen de CLTV suficiente (`MIN_CLTV_MARGIN_BLOCKS`).
4. **FUNDING**: `FundPsbt` elige y **bloquea (lease)** UTXOs con un `lock_id` propio del swap, y `FinalizePsbt` firma. **No se transmite nada.** La tx se verifica de forma independiente (destino, monto, inputs, fee no mayor al cobrado) y se guarda en la DB con su txid → `SIGNED`. Si no hay fondos, el fee real supera lo cobrado o no queda margen de CLTV → `CANCELING`.
5. **Settle** de la hold invoice → `PAID`. Recién ahí la plata LN es del servicio.
6. **Publicación** de la tx guardada → `BROADCASTED`. Reintentarla es idempotente: siempre es la misma tx firmada, así que es imposible pagar dos veces.

Garantías:
- Cada paso es re-ejecutable tras una caída en cualquier punto. Un resultado ambiguo de LND (timeout, conexión cortada) nunca se interpreta como fracaso: se vuelve a consultar el estado real.
- Cada transición es un compare-and-set sobre el estado guardado, y hay como máximo **un payout en vuelo** a la vez.
- Un único proceso: el worker toma un lock exclusivo de archivo (`WORKER_LOCK_FILE`). Un segundo proceso (otro `--workers` de uvicorn, otro contenedor sobre el mismo volumen) se niega a arrancar.
- **Detección de pagos solo por `SubscribeSingleInvoice`**, una suscripción por swap `PENDING`, sin polling de invoices. Al suscribirse (al arrancar o al reconectar un stream cortado), LND manda primero el estado actual de la invoice, así que no se pierden eventos. Los watchers solo despiertan al worker: no deciden ni escriben en la DB; el worker vuelve a consultar el estado en LND y aplica la máquina de estados. Si hay más swaps pendientes que `MAX_WATCHED_INVOICES`, se rechazan swaps nuevos (503), y al arrancar el servicio se niega a iniciar, porque una invoice sin suscripción no se detectaría nunca.

### 🚨 `MANUAL_REVIEW`

Si se rompe un invariante que protege fondos (p. ej. la invoice se settleó por fuera del flujo, o la tx fue rechazada **después** del settle, en cuyo caso **se le debe el payout al usuario**), el swap pasa a `MANUAL_REVIEW` con el motivo en la columna `error` y el proceso termina. **El servicio no arranca mientras exista algún swap en ese estado.** Para resolverlo: revisar el caso en LND/bitcoind, actuar a mano (p. ej. publicar la `raw_tx` guardada) y recién entonces cambiar el estado en la DB.

---

## 🚀 Requisitos Previos

- **Python 3.12+** (para ejecución local) o **Docker + Docker Compose**
- Un nodo LND **v0.20.x** (los protos vendorizados en `proto/` están fijados a la versión de `proto/LND_VERSION`) con gRPC accesible, fondos on-chain y liquidez de canales.

---

## ⚙️ Configuración (`.env`)

Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

Parámetros disponibles en [.env](file:///home/lucas/proj/ln2oc/.env):

| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `LND_GRPC_HOST` | Host y puerto gRPC de LND | `127.0.0.1:10001` |
| `LND_TLS_SERVER_NAME` | Nombre a verificar en el cert TLS de LND si el host usado no está en sus SANs | vacío |
| `LND_MACAROON_PATH` | Ruta absoluta al archivo `admin.macaroon` | `/ruta/.../admin.macaroon` |
| `LND_TLS_CERT_PATH` | Ruta absoluta al certificado `tls.cert` | `/ruta/.../tls.cert` |
| `BITCOIN_NETWORK` | Red Bitcoin objetivo (`regtest`, `testnet`, `mainnet`) | `regtest` |
| `SWAP_FEE_RATE` | Tasa de comisión del servicio (spread) | `0.006` (0.6%) |
| `MIN_SWAP_SAT` | Monto mínimo permitido en satoshis | `1000` |
| `MAX_SWAP_SAT` | Monto máximo permitido en satoshis | `50000000` |
| `MIN_PAYOUT_SAT` | Límite mínimo de polvo (dust limit) | `546` |
| `MIN_SAT_PER_VBYTE` | Tasa de minería mínima (sat/vB) | `1` |
| `MAX_SAT_PER_VBYTE` | Si LND estima más que esto, se rechazan swaps / se reembolsa | `500` |
| `FEE_TARGET_CONF` | Bloques objetivo para la estimación de fee | `2` |
| `ONCHAIN_MIN_CONFS` | Confirmaciones mínimas de los UTXOs usados para pagar | `1` |
| `UTXO_LEASE_SECONDS` | Duración del lease de UTXOs de un payout en vuelo | `86400` |
| `INVOICE_EXPIRY_SECONDS` | Expiración de la hold invoice | `3600` |
| `HOLD_INVOICE_CLTV_EXPIRY` | CLTV final pedido para los HTLC de la hold invoice | `144` |
| `MIN_CLTV_MARGIN_BLOCKS` | Margen mínimo de CLTV para settlear; si no alcanza, se reembolsa | `40` |
| `WORKER_LOCK_FILE` | Lock de proceso único | `<db>.worker.lock` |
| `WORKER_RETRY_INTERVAL_SECONDS` | Reintento de nuestras operaciones en curso (fund/settle/publish/cancel) mientras LND no responde | `2` |
| `MAX_WATCHED_INVOICES` | Suscripciones simultáneas máximas; por encima se rechazan swaps nuevos | `5000` |
| `DOMAIN` | Dominio para metadatos de Lightning Address | `127.0.0.1:8000` |
| `EXTERNAL_URL` | URL pública o base del servicio | `http://127.0.0.1:8000` |
| `DATABASE_URL` | Conexión SQLAlchemy a la base SQLite | `sqlite:///./ln2oc.db` |
| `LOG_LEVEL` | Nivel de logs (`INFO`, `DEBUG`, `WARNING`) | `INFO` |

---

## 🛠️ Opción 1: Correr Localmente (Entorno Virtual)

### 1. Crear e inicializar el entorno virtual
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 2. Generar los stubs gRPC de LND
```bash
PYTHON=.venv/bin/python scripts/gen_protos.sh
```
Genera `app/lnrpc/` (no se versiona) a partir de `proto/`. Para cambiar de versión de LND, reemplazar los `.proto` en `proto/` y actualizar `proto/LND_VERSION`.

### 3. Iniciar el servidor
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```
**Un solo proceso**: un segundo proceso se niega a arrancar por el lock exclusivo.

El servidor quedará escuchando en `http://localhost:8000`. Al iniciar:
- Toma el lock de proceso único.
- Crea las tablas y verifica que el schema coincida con los modelos (no hay migraciones: con una DB vieja se niega a arrancar).
- Se niega a arrancar si hay swaps en `MANUAL_REVIEW` o si LND está en otra red que `BITCOIN_NETWORK`.
- Se suscribe a todas las invoices pendientes e inicia el worker en un hilo dedicado, que retoma cualquier swap en curso desde su estado guardado.

---

## 🐳 Opción 2: Correr con Docker Compose

Docker Compose genera los stubs gRPC en el build, monta la base SQLite en un volumen nombrado (`ln2oc_data`) y las credenciales de LND en modo sólo lectura (`ro`). El contenedor corre como usuario no-root con uid `APP_UID` (por defecto `1000`), que debe poder leer el macaroon. Por defecto se conecta a `host.docker.internal:10001` (`DOCKER_LND_GRPC_HOST`).

> Ante un `MANUAL_REVIEW` el contenedor entra en un loop de reinicios que se niegan a arrancar. Es intencional: el servicio queda caído y visible hasta que alguien lo resuelva.

```bash
docker compose up -d --build
```

Para ver los logs en tiempo real:
```bash
docker compose logs -f ln2oc
```

Para detener el servicio:
```bash
docker compose down
```

---

## 🧪 Cómo Probarlo

### 1. Ejecutar la Suite Completa de Tests (E2E Regtest)
El proyecto incluye tests de integración que prueban contra tus nodos reales de Polar (`polar-n3-Kross`, `polar-n3-User` y `polar-n3-backend1`):

```bash
PYTHONPATH=. .venv/bin/pytest tests -v
```

Los tests corren contra Polar (Kross gRPC `10001`, User gRPC `10002`, bitcoind `polar-n3-backend1`) y verifican:
- Validación de direcciones y conversión a scriptPubKey, montos fuera de rango, saldo insuficiente.
- Lock de proceso exclusivo.
- **Flujo end-to-end completo** con verificación en bitcoind de que el destino recibió exactamente el payout una sola vez.
- **Reembolso** (invoice cancelada) cuando no hay fondos al momento del pago, cuando el fee real supera lo cobrado o cuando no hay margen de CLTV.
- **Fallos ambiguos inyectados**: la respuesta de `FundPsbt`, del settle o de la publicación se pierde después de que LND ejecutó la operación. En todos los casos se paga exactamente una vez.
- **Reinicio a mitad de payout**: un worker nuevo retoma la tx firmada y guardada.
- **Worker real por suscripción**: detecta pagos de swaps pendientes al arrancar y de swaps nuevos, detecta invoices canceladas, paga varios pagos simultáneos uno después del otro y se niega a arrancar si no puede suscribirse a todos los pendientes.
- **Fail loud**: invoice settleada por fuera del flujo y tx rechazada después del settle → `MANUAL_REVIEW` y el worker no procesa nada más.

---

### 2. Probar Manualmente con cURL

#### Paso A: Consultar metadata de la Lightning Address (Paso 1 LNURL-Pay)
```bash
curl -s http://127.0.0.1:8000/.well-known/lnurlp/bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz | jq
```

Respuesta esperada:
```json
{
  "tag": "payRequest",
  "callback": "http://127.0.0.1:8000/lnurlp/cb?btc_address=bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz",
  "minSendable": 1000000,
  "maxSendable": 50000000000,
  "metadata": "[[\"text/plain\", \"Swap out BTC to bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz\"], [\"text/identifier\", \"bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz@127.0.0.1:8000\"]]",
  "commentAllowed": 0
}
```

#### Paso B: Solicitar la Hold Invoice (Paso 2 LNURL-Pay)
Solicitar swap para 100,000 sats (100,000,000 millisatoshis):

```bash
curl -s "http://127.0.0.1:8000/lnurlp/cb?btc_address=bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz&amount=100000000" | jq
```

Respuesta:
```json
{
  "pr": "lnbcrt1u1p40...",
  "routes": []
}
```

#### Paso C: Pagar la Factura
Paga el `pr` devuelto desde tu wallet Lightning (o nodo Polar del usuario). Inmediatamente:
- El worker detectará el pago retenido.
- Fondeará, firmará y guardará la tx de payout (sin transmitirla).
- Liquidará la factura en Lightning.
- Transmitirá la tx guardada a `bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz`.
