# Tests de ln2oc

Son tests de integración contra una red **Polar** en regtest. Si Polar no está corriendo, fallan todos.

| Nodo | Contenedor | gRPC | Rol |
|---|---|---|---|
| Kross | `polar-n3-Kross` | `127.0.0.1:10001` (REST 8081) | corre el servicio, tiene el saldo on-chain |
| User | `polar-n3-User` | `127.0.0.1:10002` (REST 8082) | el pagador (`Payer` en `conftest.py`) |
| bitcoind | `polar-n3-backend1` | RPC `polaruser`/`polarpass` | minar, inspeccionar tx, direcciones de destino |

Credenciales en `/home/lucas/.polar/networks/3/volumes/lnd/<Nodo>/`. Kross tiene canal hacia User y ~1,1 BTC on-chain; LND estima 25 sat/vB en regtest.

## Patrones

- `env` (fixture): DB SQLite nueva en `tmp_path` y un `SwapWorker` cuyo `on_fatal` solo registra el motivo en vez de matar el proceso.
- `insert_swap(...)`: crea una hold invoice real en Kross y la fila `PENDING`, salteando las validaciones de `create_swap`. `fee_rate_sat_vb` por defecto es la estimación actual.
- `tick_until(env, swap_id, statuses)`: avanza un worker que no corre en un hilo; llama a `worker.notify(swap_id)` antes de cada tick para simular el aviso de la detección de pagos. **Cuando se reemplace la suscripción por polling, revisar este helper y los tests `test_subscription_*` / `test_startup_refuses_more_pending_swaps_than_it_can_watch`.**
- `ambiguous_once(real)`: ejecuta la llamada real a LND y después tira `LndUnavailable`, simulando una respuesta perdida. Con eso se prueba que nunca se paga dos veces.
- `assert_paid_exactly_once`: verifica en bitcoind que el destino recibió exactamente el payout una sola vez, que la invoice quedó `SETTLED` y que los leases son solo los de esa tx.
- Después de cada payout, `mine_blocks(1)` para que el cambio confirme (los payouts usan `ONCHAIN_MIN_CONFS=1`).
- Monkeypatchear métodos de `lnd_client` (instancia global) para inyectar fallos; `monkeypatch.undo()` si el test necesita después la llamada real.
