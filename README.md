# ln2oc ⚡ ➔ ₿

Servicio minimalista y confiable de **Lightning → Bitcoin On-chain Swap-out** implementado en Python 3.12+ con FastAPI, SQLite (SQLAlchemy 2.x), la API gRPC de LND y Docker Compose.

- **Pensado para montos chicos**: usuarios que quieren pasar a on-chain hasta 1.000.000 sats por swap (`MAX_SWAP_SAT`), con una comisión del 0,7 % por defecto (`SWAP_FEE_RATE`, configurable).
- **Servicio aislado**: corre con su propio nodo LND dedicado y su propio dominio. No lo corras en tu nodo principal ni en uno con mucha plata.
- **Levantá tu propia instancia**: cualquiera puede correr la suya, con su nodo, su dominio y su comisión.
- **Saldo on-chain manual**: en esta versión, reponer el saldo on-chain del nodo (convirtiendo en bloque lo que se juntó en Lightning, o cerrando canales) queda a cargo del operador.

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
1. **La tx on-chain se arma recién cuando la invoice Lightning está `SETTLED`.** Con la invoice en `ACCEPTED` solo se aplican las reglas de negocio (saldo, dust).
2. **Si no hay saldo on-chain cuando llega el pago, se cancela la hold invoice** y los sats del pagador nunca salen de su wallet.
3. **Pánico controlado, no casos bordes**: todo lo que no es una regla de negocio deja el swap en `MANUAL_REVIEW` y frena el proceso. No se escribe código para atajar casos bordes (cada uno suma superficie de ataque); se resuelven a mano y se atacan recién cuando pasan.

```text
PENDING ──(invoice ACCEPTED)──► INVOICE_HOLD ──(settle + tx enviada, en la misma vuelta)──► SUCCESS
   │                                │
   ▼                                ▼
EXPIRED (nunca se pagó)          FAILED (invoice cancelada, el pagador no pierde nada)
```

1. **LNURL-Pay**: valida la dirección y el monto y guarda `gross_sat` = monto − comisión. **No estima minería** y **no reserva saldo**: si el saldo gastable menos `ONCHAIN_RESERVE_SAT` ya no alcanza, rechaza de entrada, pero las invoices sin pagar no bloquean liquidez.
2. **Hold invoice** (`AddHoldInvoice`) con `cltv_expiry` explícito.
3. **Pago retenido**: el polling ve la invoice `ACCEPTED` → `INVOICE_HOLD`.
4. **Cada vuelta**, si la wallet on-chain tiene alguna tx sin confirmar (entrante o saliente, incluido el payout anterior), no se hace nada más. Si no, se pagan **todos** los `INVOICE_HOLD` en **una sola tx** (un output por swap), del más viejo al más nuevo:
   - una dirección que ya está en la tx → `FAILED` (reembolso);
   - se acumula `gross_sat` mientras entre en el saldo gastable menos `ONCHAIN_RESERVE_SAT` (10k: así el cambio nunca queda en dust); desde el primero que no entra, ese y **todos los que siguen** → `FAILED`;
   - minería: la estimación de LND para esa tx (`EstimateFee`, a la tasa del momento) **+ 20 %**, repartida en partes iguales. Lo cobrado de más queda en el cambio (para la casa). Si un payout queda en dust → `FAILED`. Si LND no puede leer el saldo o estimar la tx (p. ej. *insufficient funds*: el bruto entra pero bruto + minería no) → `MANUAL_REVIEW`, sin haber cobrado nada.

   $$\text{payout} = \text{gross\_sat} - \left\lceil \frac{1{,}2 \times \text{minería estimada de la tx}}{\text{swaps en la tx}} \right\rceil$$
5. **Settle** de cada invoice, `FundPsbt` con los payouts a la misma tasa de LND que usó `EstimateFee` (mismo `target_conf`, sin truncarla a sat/vB enteros), `FinalizePsbt`, verificación independiente (cada destino una sola vez con su payout, a lo sumo un output de cambio, inputs = los UTXOs que LND reservó, minería real ≤ lo cobrado), publicación y `SUCCESS` con el txid y la raw tx. Todo en la misma vuelta: **cualquier falla desde el primer settle → `MANUAL_REVIEW`** (*USER IS OWED*), sin reintentos.

Garantías:
- Cada transición es un compare-and-set sobre el estado guardado.
- Un único proceso: el worker toma un lock exclusivo de archivo (`WORKER_LOCK_FILE`). Un segundo proceso (otro `--workers` de uvicorn, otro contenedor sobre el mismo volumen) se niega a arrancar.
- Una caída a mitad de un payout deja un `INVOICE_HOLD` con su invoice `SETTLED`: la vuelta siguiente lo manda a `MANUAL_REVIEW`. Nunca se retoma un payout solo.
- **Detección de pagos por polling síncrono**, desde el mismo hilo del worker: cada `INVOICE_POLL_INTERVAL_SECONDS` (60 s por defecto) consulta con `LookupInvoice` cada swap `PENDING`, de a uno y en orden de creación. No hay suscripciones ni un hilo por invoice: el trabajo está acotado por `MAX_PENDING_SWAPS` (`PENDING` + `INVOICE_HOLD`; por encima se rechazan swaps nuevos con 503), que también acota el tamaño de la tx. El primer barrido corre al arrancar. Mientras haya pagos retenidos, el worker reintenta cada `WORKER_RETRY_INTERVAL_SECONDS` (sin volver a consultar los `PENDING`), así se pagan apenas confirma la tx que los frenaba.

### 🚨 `MANUAL_REVIEW`

Todo lo que no es una regla de negocio (la invoice se settleó por fuera del flujo, una respuesta de LND perdida, LND que no puede leer el saldo o estimar el payout antes del settle, el fondeo o la publicación fallan **después** del settle, en cuyo caso **se le debe el payout al usuario**) deja los swaps involucrados en `MANUAL_REVIEW` con el motivo en la columna `error`, y el proceso termina. **El servicio no arranca mientras exista algún swap en ese estado.** Para resolverlo: revisar el caso en LND/bitcoind (la raw tx de cada payout queda en el log antes de publicarse), actuar a mano y recién entonces cambiar el estado en la DB.

---

## 🚀 Requisitos Previos

- **Python 3.12+** (para ejecución local) o **Docker + Docker Compose**
- Un nodo LND **v0.20.x** (los protos vendorizados en `proto/` están fijados a la versión de `proto/LND_VERSION`) con gRPC accesible, fondos on-chain y liquidez de canales.

---

## ⚙️ Configuración (`.env`)

Copia la muestra que corresponda:

```bash
cp .env.dev .env     # desarrollo: regtest con Polar
cp .env.prod .env    # producción: mainnet con el LND del compose (ver docs/prod.md)
```

Parámetros disponibles en [.env](file:///home/lucas/proj/ln2oc/.env):

| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `LND_GRPC_HOST` | Host y puerto gRPC de LND | `127.0.0.1:10001` |
| `LND_TLS_SERVER_NAME` | Nombre a verificar en el cert TLS de LND si el host usado no está en sus SANs | vacío |
| `LND_MACAROON_PATH` | Ruta absoluta al archivo `admin.macaroon` | `/ruta/.../admin.macaroon` |
| `LND_TLS_CERT_PATH` | Ruta absoluta al certificado `tls.cert` | `/ruta/.../tls.cert` |
| `BITCOIN_NETWORK` | Red Bitcoin objetivo (`regtest`, `testnet` = testnet3, `testnet4`, `mainnet`). Para probar en testnet4 ver [`docs/testnet4.md`](docs/testnet4.md) | `regtest` |
| `SWAP_FEE_RATE` | Tasa de comisión del servicio (spread) | `0.007` (0.7%) |
| `MIN_SWAP_SAT` | Monto mínimo permitido en satoshis | `1000` |
| `MAX_SWAP_SAT` | Monto máximo permitido en satoshis | `1000000` |
| `MIN_PAYOUT_SAT` | Límite mínimo de polvo (dust limit) | `546` |
| `MIN_SAT_PER_VBYTE` | Tasa de minería mínima (sat/vB) | `1` |
| `MAX_SAT_PER_VBYTE` | Si LND estima más que esto al armar el payout, se reembolsa a todos | `500` |
| `FEE_TARGET_CONF` | Bloques objetivo para la estimación de fee | `2` |
| `ONCHAIN_RESERVE_SAT` | Saldo on-chain que nunca se paga: el cambio del payout siempre queda por encima de dust (si no, LND lo suma a la minería y el payout falla después del settle) | `10000` |
| `ONCHAIN_MIN_CONFS` | Confirmaciones mínimas de los UTXOs usados para pagar | `1` |
| `INVOICE_EXPIRY_SECONDS` | Expiración de la hold invoice | `3600` |
| `HOLD_INVOICE_CLTV_EXPIRY` | CLTV final pedido para los HTLC de la hold invoice | `144` |
| `WORKER_LOCK_FILE` | Lock de proceso único | `<db>.worker.lock` |
| `INVOICE_POLL_INTERVAL_SECONDS` | Cada cuánto se consultan todas las invoices pendientes, de a una (1–600) | `60` |
| `WORKER_RETRY_INTERVAL_SECONDS` | Reintento mientras hay pagos retenidos o LND no responde | `2` |
| `MAX_PENDING_SWAPS` | Swaps `PENDING` + `INVOICE_HOLD` máximos (1–1000); por encima se rechazan swaps nuevos. Acota también el tamaño de la tx | `1000` |
| `DOMAIN` | Dominio para metadatos de Lightning Address | `127.0.0.1:8000` |
| `EXTERNAL_URL` | URL pública o base del servicio | `http://127.0.0.1:8000` |
| `DATABASE_URL` | Conexión SQLAlchemy a la base SQLite | `sqlite:///./ln2oc.db` |
| `FRONTEND_URL` | Sitio web (lo sirve otro servidor); `GET /` redirige acá. Sin valor, `/` da 404 | — |
| `GIT_COMMIT` | Commit que informa `/api/info` (se pasa en el build de Docker); sin valor usa `git rev-parse HEAD` | — |
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
- Inicia el worker en un único hilo dedicado: retoma cualquier swap en curso desde su estado guardado y hace el primer barrido de invoices pendientes.

---

## 🐳 Opción 2: Correr con Docker Compose

Docker Compose genera los stubs gRPC en el build, monta la base SQLite en un volumen nombrado (`ln2oc_data`) y las credenciales de LND en modo sólo lectura (`ro`). El contenedor corre como usuario no-root con uid `APP_UID` (por defecto `1000`), que debe poder leer el macaroon. Por defecto se conecta a `host.docker.internal:10001` (`DOCKER_LND_GRPC_HOST`). Todos los parámetros salen de `.env` (`env_file`); `LND_MACAROON_PATH` y `LND_TLS_CERT_PATH` son rutas del host que se montan en el contenedor, y si no existen el contenedor no arranca.

En producción, `COMPOSE_PROFILES=lnd` suma el servicio `lnd` (LND v0.20 en neutrino, sin puertos publicados) y los scripts de `scripts/lnd/` crean, recuperan y respaldan la wallet: ver [`docs/prod.md`](docs/prod.md).

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

## 🌐 Sitio web (`web/`)

Sitio estático en React + Vite (multi-página: `/`, `/usuario/`, `/operadores/`, `/flujo/`, `/arquitectura/`), con el contenido y el estilo del artifact de documentación. **Lo sirve su propio servidor** (servicio `web` de Docker Compose: nginx en el puerto `8080`). El servicio de swaps no sirve archivos del sitio: solo redirige `GET /` a `FRONTEND_URL`.

El sitio lee los valores reales de la instancia de `GET /api/info` (red, dominio, comisión, límites, tasa de minería actual y tamaño del último payout, versión y commit). Si la API no responde, muestra los valores por defecto.

```bash
cd web
npm ci
VITE_API_URL=http://127.0.0.1:8000 npm run dev   # http://127.0.0.1:5173
npm test                                         # validador de direcciones y cuenta de fees
npm run build                                    # genera web/dist
```

Con Docker: `PUBLIC_API_URL=https://ln2oc.com docker compose up -d --build web` (la URL de la API queda fija en el build). Para que `/api/info` informe el commit dentro del contenedor: `GIT_COMMIT=$(git rev-parse --short HEAD) docker compose build ln2oc`.

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
- **Reembolso** (invoice cancelada) cuando no hay saldo al momento del pago, cuando el payout quedaría en dust o cuando la tasa supera `MAX_SAT_PER_VBYTE`.
- **Nada on-chain antes del cobro**: `FundPsbt` solo se llama con la invoice ya `SETTLED`. El usuario paga la estimación de LND + 20 % y la minería real queda por debajo.
- **Varios pagos en una tx** (`tests/test_payout_rules.py`): retenidos mientras la wallet tiene una tx sin confirmar, después se pagan juntos; desde el primero que no entra en el saldo se reembolsan todos los que siguen; nunca se paga la reserva `ONCHAIN_RESERVE_SAT`; una dirección repetida se reembolsa.
- **Pánicos controlados**: invoice settleada por fuera del flujo, LND que rechaza la estimación del payout antes del settle (la invoice queda `ACCEPTED`), caída después del settle, respuesta perdida de LND (settle, fondeo, firma o publicación), publicación rechazada → `MANUAL_REVIEW` y el worker no procesa nada más.
- **Worker real por polling**: detecta pagos retenidos al arrancar, swaps nuevos e invoices canceladas.

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
  "maxSendable": 1000000000,
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
