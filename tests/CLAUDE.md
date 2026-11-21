# Tests de ln2oc

Son tests de integración contra una red **Polar** en regtest. Si Polar no está corriendo, fallan todos.

| Nodo | Contenedor | gRPC | Rol |
|---|---|---|---|
| Kross | `polar-n3-Kross` | `127.0.0.1:10001` (REST 8081) | corre el servicio, tiene el saldo on-chain |
| User | `polar-n3-User` | `127.0.0.1:10002` (REST 8082) | el pagador (`Payer` en `conftest.py`) |
| bitcoind | `polar-n3-backend1` | RPC `polaruser`/`polarpass` | minar, inspeccionar tx, direcciones de destino |

Credenciales en `/home/lucas/.polar/networks/3/volumes/lnd/<Nodo>/`. **Cada corrida pasa liquidez de User a Kross**: si muchos tests fallan con "invoice still open" o pagos que no llegan a `ACCEPTED`, mirar `lncli --network regtest --lnddir /home/lnd/.lnd channelbalance` en `polar-n3-User`. Para rebalancear: User hace `addinvoice --amt 8000000` y Kross la paga con `payinvoice --force`. Antes, cancelar las hold invoices `ACCEPTED` que hayan quedado en Kross de tests abortados. Kross tiene canal hacia User y ~1,1 BTC on-chain; LND estima 25 sat/vB en regtest.

## Patrones

- `env` (fixture): DB SQLite nueva en `tmp_path` y un `SwapWorker` cuyo `on_fatal` solo registra el motivo en vez de matar el proceso.
- `insert_swap(Session, amount_sat, gross_sat, address)`: crea una hold invoice real en Kross y la fila `PENDING`, salteando las validaciones de `create_swap`. La minería no se guarda: se fija al firmar.
- Para controlar la tasa al firmar: monkeypatchear `app.worker.current_fee_rate_sat_per_vbyte` (la 1ª llamada es el chequeo antes del settle, la 2ª la firma). `_spike_after_settle` simula una suba después del settle (se paga hasta el tope `max_miner_fee_sat`).
- `tick_until(env, swap_id, statuses)`: avanza a mano un worker que no corre en un hilo; cada tick es un barrido completo de las `PENDING` (`run_tick_guarded()` con `poll_pending=True` por defecto).
- `_polling_worker(env, poll_interval)`: worker real en su hilo. Con `poll_interval=300` solo el barrido inicial ve los pagos, lo que sirve para probar que los pagos retenidos que esperan el slot avanzan por el retry rápido y no por el próximo barrido.
- `ambiguous_once(real)`: ejecuta la llamada real a LND y después tira `LndUnavailable`, simulando una respuesta perdida. Con eso se prueba que nunca se paga dos veces.
- `assert_paid_exactly_once`: verifica en bitcoind que el destino recibió exactamente el payout una sola vez, que la invoice quedó `SETTLED` y que los leases son solo los de esa tx.
- Después de cada payout, `mine_blocks(1)`: el siguiente pago espera retenido hasta que no quede ninguna tx de la wallet sin confirmar. El fixture `env` mina un bloque al arrancar si quedó alguna (p. ej. de un run abortado). `send_to_kross_unconfirmed(btc)` genera un depósito entrante sin confirmar.
- Monkeypatchear métodos de `lnd_client` (instancia global) para inyectar fallos; `monkeypatch.undo()` si el test necesita después la llamada real.
