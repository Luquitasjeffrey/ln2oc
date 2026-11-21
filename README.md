# ln2oc ⚡ ➔ ₿

Servicio minimalista y confiable de **Lightning → Bitcoin On-chain Swap-out** implementado en Python 3.12+ con FastAPI, SQLite (SQLAlchemy 2.x), la API REST de LND y Docker Compose.

---

## 📖 ¿Cómo funciona?

El servicio expone un endpoint estándar de **Lightning Address (LNURL-Pay)** donde el "usuario" es la dirección de destino on-chain:

```text
<DIRECCION_BITCOIN>@tudominio.com
```

Por ejemplo:
- Regtest: `bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz@127.0.0.1:8000`
- Mainnet: `bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr@swapservice.com`

### Flujo de Ejecución:
1. **Validación de dirección**: Valida que la dirección sea sintáctica y criptográficamente válida (Bech32, Bech32m Taproot, Base58 P2PKH/P2SH) para la red configurada (`regtest`, `testnet`, `mainnet`).
2. **Cálculo de comisión y payout**:
   $$\text{payout} = \lfloor \text{amount\_sat} \times (1 - \text{SWAP\_FEE\_RATE}) \rfloor - \text{miner\_fee\_sat}$$
   Por defecto la comisión es del `0.6%` (`amount_sat * 994 // 1000 - miner_fee_sat`).
3. **Reserva atómica de fondos**: Verifica en SQLite que el saldo on-chain confirmado del nodo LND menos todas las operaciones activas concurrentes cubra el monto del swap.
4. **Generación de Hold Invoice**: Se crea una factura Lightning condicional (`/v2/invoices/hodl`) con expiración de 1 hora.
5. **Detección de pago (`ACCEPTED`)**: El worker en segundo plano detecta cuando el pagador envía los satoshis por Lightning (retenidos por LND).
6. **Emisión de transacción On-chain**: Se envía la transacción de Bitcoin vía `/v1/transactions` de LND hacia la dirección de destino.
7. **Persistencia del TXID**: El hash de la transacción on-chain (`txid`) y el estado `BROADCASTED` se guardan en la base de datos **antes** de liquidar la factura.
8. **Liquidación (`SETTLE`)**: Con la transacción on-chain transmitida, se libera el `preimage` secreto para liquidar la Hold Invoice y cobrar los satoshis en Lightning.
9. **Manejo de fallos y recuperación**:
   - Si la transacción on-chain falla, la Hold Invoice se cancela inmediatamente devolviéndole los fondos al pagador.
   - Si el servicio se reinicia tras transmitir una transacción on-chain, al arrancar liquida automáticamente las facturas pendientes asociadas a transacciones ya emitidas.

---

## 🚀 Requisitos Previos

- **Python 3.12+** (para ejecución local) o **Docker + Docker Compose**
- Un nodo LND con API REST habilitada, fondos on-chain y liquidez de canales.

---

## ⚙️ Configuración (`.env`)

Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

Parámetros disponibles en [.env](file:///home/lucas/proj/ln2oc/.env):

| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `LND_REST_HOST` | Host y puerto REST de LND | `127.0.0.1:8081` |
| `LND_MACAROON_PATH` | Ruta absoluta al archivo `admin.macaroon` | `/ruta/.../admin.macaroon` |
| `LND_TLS_CERT_PATH` | Ruta absoluta al certificado `tls.cert` | `/ruta/.../tls.cert` |
| `BITCOIN_NETWORK` | Red Bitcoin objetivo (`regtest`, `testnet`, `mainnet`) | `regtest` |
| `SWAP_FEE_RATE` | Tasa de comisión del servicio (spread) | `0.006` (0.6%) |
| `MIN_SWAP_SAT` | Monto mínimo permitido en satoshis | `1000` |
| `MAX_SWAP_SAT` | Monto máximo permitido en satoshis | `50000000` |
| `MIN_PAYOUT_SAT` | Límite mínimo de polvo (dust limit) | `546` |
| `MIN_SAT_PER_VBYTE` | Tasa de minería mínima / fallback (sat/vB) | `1` |
| `DOMAIN` | Dominio para metadatos de Lightning Address | `127.0.0.1:8000` |
| `EXTERNAL_URL` | URL pública o base del servicio | `http://127.0.0.1:8000` |
| `DATABASE_URL` | Conexión SQLAlchemy a la base SQLite | `sqlite:///./swapservice.db` |
| `LOG_LEVEL` | Nivel de logs (`INFO`, `DEBUG`, `WARNING`) | `INFO` |

---

## 🛠️ Opción 1: Correr Localmente (Entorno Virtual)

### 1. Crear e inicializar el entorno virtual
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Iniciar el servidor
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

El servidor quedará escuchando en `http://localhost:8000`. Al iniciar:
- Crea automáticamente las tablas en SQLite con modo WAL.
- Inicia el worker asíncrono en background para monitorear y procesar swaps.
- Ejecuta el proceso de recuperación ante reinicios.

---

## 🐳 Opción 2: Correr con Docker Compose

Docker Compose monta de forma persistente la base de datos SQLite en un volumen nombrado (`swap_data`) y los archivos de credenciales de LND en modo sólo lectura (`ro`).

```bash
docker compose up -d --build
```

Para ver los logs en tiempo real:
```bash
docker compose logs -f swapservice
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
PYTHONPATH=. .venv/bin/pytest tests/test_swap_e2e.py -v
```

Los tests verifican:
- Validación de direcciones (Bech32, Taproot y Base58 válidos/inválidos).
- Rechazo de montos fuera de rango o por debajo del dust limit.
- Control de saldo insuficiente y aislamiento de reservas concurrentes.
- Cancelación de Hold Invoice si falla la transacción on-chain.
- Recuperación y liquidación automática tras caídas del servidor.
- **Flujo end-to-end completo**: Node B paga Hold Invoice con Lightning → Node A envía BTC on-chain → Se mina el bloque → Node B confirma recepción y la factura queda liquidada.

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
- El worker detectará el pago.
- Transmitirá los sats a `bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz`.
- Guardará el `txid` en la base de datos.
- Liquidará la factura en Lightning.
