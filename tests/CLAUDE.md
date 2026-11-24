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
- `insert_swap(Session, amount_sat, gross_sat, address)`: crea una hold invoice real en Kross y la fila `PENDING`, salteando las validaciones de `create_swap`. La minería no se guarda: se cobra al pagar.
- `tick_until(env, swap_id, statuses)`: avanza a mano un worker que no corre en un hilo; cada tick es un barrido completo de las `PENDING` (`run_tick_guarded()` con `poll_pending=True` por defecto).
- `_polling_worker(env, poll_interval)`: worker real en su hilo. Con `poll_interval=300` solo el barrido inicial ve los pagos.
- `ambiguous_once(real)`: ejecuta la llamada real a LND y después tira `LndUnavailable`, simulando una respuesta perdida. Desde el primer settle eso tiene que terminar en `MANUAL_REVIEW`, nunca en un reintento.
- `_ProcessDied` (`BaseException`): se escapa de `run_tick_guarded` como un `kill -9`, para probar caídas a mitad del payout.
- `assert_paid_exactly_once`: verifica en bitcoind que el destino recibió exactamente el payout una sola vez, que payout + minería cobrada = gross y que la invoice quedó `SETTLED`.
- Varios pagos en una tx (`test_payout_rules.py`): `_held_while_wallet_busy(env, payer, grosses)` deja un depósito sin confirmar, paga un swap por gross (quedan en `INVOICE_HOLD`) y mina: el tick siguiente los paga juntos. `_tick_all` avanza hasta que todos terminan y `_assert_one_tx_pays` verifica una sola tx con un output por swap más el cambio. Para achicar el saldo: monkeypatchear `SwapWorker._spendable_sat`.
- Después de cada payout, `mine_blocks(1)`: el siguiente pago espera retenido hasta que no quede ninguna tx de la wallet sin confirmar. El fixture `env` mina un bloque al arrancar si quedó alguna (p. ej. de un run abortado). `send_to_kross_unconfirmed(btc)` genera un depósito entrante sin confirmar.
- Monkeypatchear métodos de `lnd_client` (instancia global) para inyectar fallos; `monkeypatch.undo()` si el test necesita después la llamada real.
- Un fatal después de fondear deja UTXOs leaseados ~10 min (`_LEASE_SECONDS`): si el test publica la tx a mano para limpiar (como `test_publish_rejected_is_fatal`), se gastan.
