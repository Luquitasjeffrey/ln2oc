# ln2oc ⚡ ➔ ₿

**Lightning → on-chain, en un paso.** Tu Lightning Address es tu dirección de Bitcoin: te pagan (o te pagás vos) por Lightning y los sats llegan on-chain a tu cold wallet.

```text
<tu dirección bc1…>@ln2oc.com
```

Y si corrés un servicio Lightning con usuarios (un exchange P2P, una wallet, un sistema de pagos), podés ofrecerles retiro on-chain sin construirlo: tu **comunidad** se lleva una parte de la comisión de cada swap que llega por vos, y para tus usuarios no cambia nada.

Servicio minimalista en Python 3.12 + FastAPI, SQLite, la API gRPC de LND y Docker Compose. Código GPLv3: cualquiera puede levantar su propia instancia.

## ¿Quién sos?

ln2oc apunta a tres tipos de usuarios, más quien quiera leer el código:

- [👤 **Usuarios finales**](#-usuario): querés recibir o mandarte sats por Lightning y que terminen en tu cold wallet.
- [🤝 **Community leaders**](#-community-leaders): corrés un servicio Lightning con usuarios y querés ofrecerles retiro on-chain, llevándote una parte de la comisión.
- [🧑‍🔧 **Operadores**](#-operador): querés correr tu propia instancia y ganar una comisión por cada swap.
- [🛠️ **Desarrolladores**](#-cómo-funciona-por-dentro): querés entender el flujo, correrlo, testearlo o integrarlo. El código está en [github.com/Luquitasjeffrey/ln2oc](https://github.com/Luquitasjeffrey/ln2oc).

---

## 👤 Usuario

### Cómo usarlo

1. **Armá tu Lightning Address**: tomá una dirección de recepción de tu cold wallet y agregale `@` y el dominio de la instancia. Por ejemplo:
   ```text
   bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr@ln2oc.com
   ```
   Solo direcciones **bech32**: SegWit (`bc1q…`) o Taproot (`bc1p…`). Las legacy (`1…`, `3…`) no, porque una Lightning Address va en minúsculas y esas distinguen mayúsculas.
2. **Pagale** desde cualquier wallet Lightning que pague a Lightning Address (Wallet of Satoshi, Phoenix, BlueWallet, ZEUS…), o pasásela a quien te tenga que pagar.
3. **Esperá el bloque**: el pago queda retenido unos segundos (hasta un minuto) mientras el nodo arma tu tx on-chain, y después llega a tu dirección en el próximo bloque.

Para qué sirve:
- **Auto-envío**: juntaste sats en una wallet caliente y te los mandás a frío, sin abrir canales ni hacer un swap a mano.
- **Cobros**: una venta, una donación, un sueldo. Quien te paga usa Lightning y vos recibís on-chain. Podés armar una dirección nueva para cada cobro.
- **Trades P2P**: en un exchange P2P que pague a Lightning Address (por ejemplo, Mostro) ponés la tuya, y cuando el vendedor libera, los sats van directo a tu cold wallet.

### Cuánto te llega

Se descuentan la **comisión del servicio** (0,7 % por defecto; cada instancia fija la suya) y la **minería de tu tx**, que se calcula al momento de pagarte: la estimación del nodo para la tx real, a la tasa de ese momento, más un 20 %. Si en esa tx van varios pagos, la minería se reparte en partes iguales.

| Un swap de 100.000 sats | sats |
| :--- | ---: |
| Pagás por Lightning | 100.000 |
| Comisión del servicio (0,7 %) | −700 |
| Minería, ejemplo (131 vB × 1 sat/vB + 20 %) | −158 |
| **Llega a tu cold wallet (aprox.)** | **99.142** |

Montos: hasta **1.000.000 sats** por swap (`MAX_SWAP_SAT`). Está pensado para montos chicos.

### En qué confiás y en qué no

- ✅ **Que el nodo tenga fondos: no hace falta confiar.** Usa *hold invoices*: tu pago queda retenido y el nodo lo cobra recién cuando tiene con qué pagarte on-chain. Si no le alcanza el saldo, cancela la invoice y los sats vuelven a tu wallet.
- ✅ **Que te paguen mal o dos veces:** antes de publicar, el servicio verifica la tx firmada (destino, monto, inputs). Nunca reintenta un pago: ante cualquier duda se frena y lo revisa una persona.
- ⚠️ **Los segundos entre el cobro y la publicación:** no es un swap atómico. Entre que el nodo cobra tu pago y publica tu tx, el operador tiene tu plata. Si algo falla ahí, el servicio se frena y el operador te debe el payout. Es custodia por segundos, no por días.

---

## 🤝 Community leaders

Si corrés un exchange P2P (por ejemplo, un nodo de Mostro), una wallet o un sistema de pagos Lightning, tus usuarios pueden retirar on-chain con ln2oc. Vos aportás los usuarios, y por cada swap que llega por tu comunidad te corresponde **un % de incentivo** (por defecto 0,1 %, de los 0,7 % de comisión; cada instancia fija los suyos). Sale de lo que se queda el operador: tus usuarios pagan lo mismo que cualquiera.

Cómo crear tu comunidad:

1. **Contactá al operador** de la instancia y dejale un contacto (Telegram, mail…), solo para coordinar los pagos.
2. **El operador te registra y te da tu handle**: el nombre de tu comunidad, en minúsculas, números y guiones (por ejemplo `mi-comunidad`).
3. **Agregá el handle en tu integración**: tu servicio resuelve la Lightning Address del usuario como siempre y le suma `?community=<handle>` a la URL de LNURL-pay:
   ```text
   GET https://ln2oc.com/.well-known/lnurlp/bc1q…?community=mi-comunidad
   ```
   El servicio lo arrastra al callback y el swap queda asociado a tu comunidad. Un handle inexistente da error 400.
4. **Cobrá lo acumulado**: el operador te liquida a mano lo adeudado de tus swaps exitosos; le pasás una invoice o una Lightning Address.

Para tus usuarios no cambia nada: usan la misma `bc1q…@ln2oc.com`, pagan lo mismo y reciben lo mismo. Una wallet común que no manda el parámetro sigue funcionando igual. En qué confiás: en el operador, para la cuenta y el pago (es una deuda de palabra, no un pago automático).

El modelo de comunidades está inspirado en [lnp2pBot](https://github.com/lnp2pBot/bot), de [@grunch](https://github.com/grunch).

---

## 🧑‍🔧 Operador

**Ganás un % por cada swap que ejecute tu nodo**: la comisión (`SWAP_FEE_RATE`, 0,7 % por defecto). La minería de cada payout la paga el usuario y no entra en ese %: la estimación de LND + 20 %, y lo cobrado de más queda para vos.

### Tu negocio: convertir en bloque

Cada swap le saca sats a tu wallet on-chain y te los devuelve en tus canales Lightning, más la comisión. **Reponer el saldo on-chain es tarea tuya**, a mano: en esta versión no está automatizado.

La premisa del negocio es que **se consigue mejor % de conversión de Lightning a on-chain con cantidades grandes**. La mayoría de los usuarios va a hacer órdenes chicas, y convertir de a poco les sale caro. Vos juntás todo ese volumen en Lightning y lo convertís **en bloques grandes**: pasar 5.000.000 sats de una vez cuesta, en %, bastante menos que de a 100.000. Esa diferencia contra la comisión es tu margen.

| Ejemplo: 50 swaps de 100.000 sats | sats |
| :--- | ---: |
| Volumen total por Lightning | 5.000.000 |
| Comisiones cobradas a los usuarios (0,7 %) | +35.000 |
| Reponer on-chain en un solo bloque (0,2 %) | −10.000 |
| **Margen antes de otros costos** | **≈ 25.000** |

Porcentajes ilustrativos y sin minería. Si en tu caso no consiguieras convertir en bloque más barato que tu comisión, el servicio no cierra por costo: lo que queda para cobrar es la comodidad (hay usuarios que pagarían, por ejemplo, 1 %). Por eso la comisión es configurable.

### Cómo reponer el saldo on-chain

Opciones ordenadas por costo con volumen. Los % no incluyen la minería de la reposición, que es un costo fijo chico por operación.

| Opción | Custodia | Costo del proveedor | Volumen | A tener en cuenta |
| :--- | :--- | ---: | :--- | :--- |
| **Tus propios sats on-chain** | no custodial | 0 % | Lo que quieras tener en Lightning | Fondeás el nodo y los swaps te los devuelven en Lightning, más la comisión. Gratis, pero no escala. |
| **Cierre cooperativo de canales** | no custodial | 0 % | Tu lado local del canal | Una sola tx (~200 vB) sin importar el monto. El costo escondido es volver a conseguir la liquidez entrante. |
| **Exchanges** (Kraken, Bitfinex, OKX, Binance…) | custodial · KYC | ≤ 0,2 % (según volumen) | Alto; con límites por operación en Lightning | Depósito LN casi siempre gratis, retiro on-chain con comisión fija: cuanto más movés, menor el %. Usalo de paso, sin dejar saldo. |
| **Lightning Loop Out** (Lightning Labs) | no custodial | 0,05 – 0,5 % | Desde ~250.000 sats | Submarine swap con `loopd` al lado de tu LND. ~0,17 % en 300.000 y ~0,33 % en 1.000.000; prepay de 30.000 sats. |
| **FixedFloat** | custodial · sin cuenta | 0,5 – 1 % | Límites por orden | 0,5 % con tasa flotante, 1 % con tasa fija. |
| **Swap servers de Electrum** (sobre Nostr) | no custodial | ~0,5 – 1 % | Según el proveedor | Cada proveedor fija su comisión. |
| **Wallets custodiales** (p. ej. Rizful) | custodial | ~0,5 % | Chico; mínimo 5.000 sats | Mandás por Lightning y enviás on-chain desde ahí. |
| **Boltz** | no custodial | 0,5 % | — | **Caído**: suspendió los swaps en agosto de 2026. |

Criterio: gana el que da **mejor % con el volumen que necesitás**; a costo parecido, primero lo self-custodial. Lo que cobra 0,5 % o más no deja margen contra el 0,7 %. Datos de noviembre de 2026: cotizá siempre antes de operar (`loop quote out <monto>`).

### Comunidades

Un proveedor de servicios Lightning con muchos usuarios (un exchange como un nodo de Mostro, una wallet, un sistema de pagos) puede ofrecerles retiro on-chain con tu instancia en vez de armar el suyo. A cambio de traerte esos usuarios, **la comunidad se lleva una parte de la comisión**: `COMMUNITY_FEE_RATE` (0,1 % por defecto) sale del `SWAP_FEE_RATE`, no se le suma al usuario.

| Un swap de 100.000 sats | sin comunidad | con comunidad |
| :--- | ---: | ---: |
| Comisión total (0,7 %) | 700 | 700 |
| Para el operador | 700 | 600 |
| Para la comunidad (0,1 %) | 0 | 100 |
| Para el usuario (antes de minería) | 99.300 | 99.300 |

Es un **hook cooperativo** sobre LNURL-pay: el integrador arma la URL agregando `?community=<name>` (por ejemplo `https://ln2oc.com/.well-known/lnurlp/bc1q…?community=mi-comunidad`), y el servicio lo arrastra al callback. Una wallet común no manda nada y no ve ninguna diferencia. Una comunidad inexistente da error 400.

Cada swap guarda `community_id`, `operator_fee_sat` y `community_fee_sat`. Lo que se le debe a una comunidad es la suma de `community_fee_sat` de sus swaps `SUCCESS` menos lo que ya le pagaste. **El pago es manual**: el alta y el registro de los pagos se hacen con dos scripts interactivos que corren dentro del contenedor:

```bash
scripts/register_community.sh            # pide name (a-z, 0-9, '-') y contact (texto libre)
scripts/withdraw_community_earnings.sh   # muestra lo adeudado; si pagás ahora, lo registra
```

Después del retiro, le pedís al admin de la comunidad una invoice o una Lightning Address y le pagás a mano.

La inspiración del modelo de comunidades viene de [lnp2pBot](https://github.com/lnp2pBot/bot), de [@grunch](https://github.com/grunch). Del lado del community leader, ver [🤝 Community leaders](#-community-leaders).

### Qué necesitás

- **Un nodo LND v0.20 dedicado** y un **dominio dedicado** con HTTPS. Nunca tu nodo principal, ni uno de routing, ni uno con mucha plata: el servicio firma transacciones solo, y si algo sale mal el daño tiene que quedar acotado a ese nodo.
- **Saldo on-chain**: el capital de trabajo entre reposiciones. Como mínimo el swap más grande que aceptes más su minería, y no mucho más. LND reserva 10.000 sats por canal anchor (hasta 100.000), y ln2oc nunca paga los últimos `ONCHAIN_RESERVE_SAT` (10.000), para que el cambio de cada payout no quede en dust.
- **Liquidez entrante** en tus canales: para que te puedan pagar, tus canales necesitan saldo del lado remoto. Comprala o pedile a peers bien conectados que te abran canales.
- **UTXOs medianos**: todos los pagos retenidos se pagan juntos en una tx, más o menos una por bloque. Con muchos UTXOs chicos la tx pesa más y los usuarios pagan más minería.
- **Estar atento**: si algo se sale de las reglas, el servicio se frena solo (ver [`MANUAL_REVIEW`](#-manual_review)) y no vuelve a arrancar hasta que lo resuelvas a mano.

Para levantarlo: [configuración](#️-configuración-env), [Docker Compose](#-opción-2-correr-con-docker-compose) y, para mainnet, [`docs/prod.md`](docs/prod.md). Para probar en testnet4: [`docs/testnet4.md`](docs/testnet4.md).

---

## 📖 Cómo funciona por dentro

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
| `COMMUNITY_FEE_RATE` | Parte de `SWAP_FEE_RATE` que se le debe a la comunidad del swap (`?community=`); no puede superar `SWAP_FEE_RATE` | `0.001` (0.1%) |
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
Paga el `pr` devuelto desde tu wallet Lightning (o nodo Polar del usuario). El pago queda retenido y:
- En el próximo barrido (cada `INVOICE_POLL_INTERVAL_SECONDS`), el worker ve la invoice `ACCEPTED` y el swap pasa a `INVOICE_HOLD`.
- Cuando la wallet on-chain no tiene ninguna tx sin confirmar, en la misma vuelta: liquida la invoice, fondea y firma la tx de payout (junto con los demás pagos retenidos), la verifica y la publica hacia `bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz`. El swap queda en `SUCCESS`.
