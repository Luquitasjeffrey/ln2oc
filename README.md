# ln2oc

Minimal Lightning → Bitcoin on-chain swap-out service.

## Stack
- Python 3.12+
- FastAPI
- SQLite + SQLAlchemy 2.x
- LND REST API
- Docker + Docker Compose
- pytest

## Overview

`ln2oc` provides a clean, reliable Lightning Address endpoint that turns Lightning payments into Bitcoin on-chain outputs:

`bc1q...@swapservice.com` or `bcrt1q...@swapservice.com`

The username is the Bitcoin destination address.

### Flow
1. **Validate destination address**: Supports Segwit v0/v1 (Taproot) and legacy addresses.
2. **Check available balance & miner fees**: Confirmed balance minus uncompleted swaps. Minimum fee rate `1 sat/vB`.
3. **Calculate payout**: `amount_sat * 994 // 1000 - miner_fee_sat` (configurable via `SWAP_FEE_RATE`).
4. **Reserve funds**: Atomic check against SQLite database to prevent concurrent double reservations.
5. **Generate LND Hold Invoice**: Client receives Lightning Hold Invoice.
6. **Detect incoming payment**: Background worker notices `ACCEPTED` state (held by LND).
7. **Broadcast on-chain**: Sends BTC to destination address via LND `/v1/transactions`.
8. **Persist TXID**: Persisted with status `BROADCASTED` *before* settling.
9. **Settle Hold Invoice**: Releases preimage to capture the Lightning payment.
10. **Error handling**: If on-chain send fails, Hold Invoice is canceled to refund the sender. If the server crashes after broadcasting, swaps are settled on restart.

---

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Environment variables:
- `LND_REST_HOST`: LND REST API endpoint (e.g. `127.0.0.1:8081`)
- `LND_MACAROON_PATH`: Path to `admin.macaroon`
- `LND_TLS_CERT_PATH`: Path to `tls.cert`
- `BITCOIN_NETWORK`: `regtest`, `testnet`, or `mainnet`
- `SWAP_FEE_RATE`: Spread rate (default `0.006` = 0.6%)
- `MIN_SWAP_SAT`: Minimum swap input in satoshis (default `1000`)
- `MAX_SWAP_SAT`: Maximum swap input in satoshis (default `50000000`)
- `MIN_PAYOUT_SAT`: Dust limit threshold (default `546`)
- `MIN_SAT_PER_VBYTE`: Fallback and minimum sat/vB fee rate (default `1`)
- `DOMAIN`: Host domain for Lightning Address metadata
- `EXTERNAL_URL`: Full base URL (e.g. `http://127.0.0.1:8000`)
- `DATABASE_URL`: SQLAlchemy connection string (`sqlite:///./swapservice.db`)

---

## Running with Docker Compose

```bash
docker compose up -d --build
```

The service mounts a persistent SQLite volume (`swap_data`) and LND certificates/macaroons read-only.

---

## Running Locally

1. Create a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start the API service:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Testing

Run tests against your Polar regtest network:

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_swap_e2e.py -v
```

Tests cover:
- Address validation (valid/invalid Bech32, Bech32m, Base58)
- Min/Max swap bounds and dust payouts
- Insufficient on-chain balance rejection
- Concurrent reservation isolation
- Failed broadcast handling and hold invoice cancellation
- Crash recovery settling already-broadcasted swaps
- Full end-to-end swap: LNURL-Pay negotiation, Hold Invoice generation, User payment, on-chain broadcast, Hold Invoice settlement, and block confirmation verification.
