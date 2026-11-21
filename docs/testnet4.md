# Prueba en testnet4

Objetivo: probar el flujo real de Lightning Address (dominio, HTTPS, proxy, wallet → servicio → payout on-chain) antes de mainnet. Es el TODO 9.

**Por qué testnet4 y no testnet3:** testnet4 (BIP-94) reemplaza a testnet3, que tiene block storms y faucets que no andan. LND lo soporta desde v0.19 (`bitcoin.testnet4=1`). Para ln2oc es `BITCOIN_NETWORK=testnet4`, y `startup_checks` espera que LND reporte `testnet4` en `GetInfo` (testnet3 aparece como `testnet`). Las direcciones son iguales que en testnet3: `tb1…`, `m/n…`, `2…`. Las invoices empiezan con `lntb`.

## Piezas

```
 payer LND (testnet4) ──canal──► LND del servicio (testnet4) ◄─gRPC─ ln2oc (:8000)
       ▲                                                                ▲
 scripts/lnaddr_pay.py  o  wallet ── HTTPS ── testnet.<dominio> (Caddy) ┘
```

1. **bitcoind testnet4** (Bitcoin Core ≥ 28) con ZMQ. LND necesita `txindex` o bloques completos: no lo pruebes con un nodo podado sin chequear antes que tu versión de LND lo soporte.
2. **LND v0.20 del servicio**, dedicado y con poca plata, igual que en mainnet.
3. **LND pagador**: un segundo LND en testnet4. Hace de "wallet": abre un canal hacia el nodo del servicio, y así el servicio ya tiene liquidez entrante sin depender de nodos públicos.
4. **Dominio con HTTPS válido**, por ejemplo `testnet.ln2oc.com`. Las wallets no aceptan HTTP ni certificados autofirmados (LUD-01; Phoenix rechaza un callback que no sea seguro).

## LND (los dos nodos)

```ini
[Bitcoin]
bitcoin.active=1
bitcoin.testnet4=1
bitcoin.node=bitcoind

[Bitcoind]
bitcoind.rpchost=127.0.0.1:48332
bitcoind.rpcuser=...
bitcoind.rpcpass=...
bitcoind.zmqpubrawblock=tcp://127.0.0.1:28332
bitcoind.zmqpubrawtx=tcp://127.0.0.1:28333
```

Los dos nodos en la misma máquina necesitan `lnddir`, `rpclisten`, `restlisten` y `listen` distintos. El macaroon debería quedar en `<lnddir>/data/chain/bitcoin/testnet4/admin.macaroon`. Es una inferencia del código de LND (`NormalizeNetwork`): verificalo al levantar.

Fondos: conseguí tBTC de un faucet de testnet4 para el nodo del servicio (los payouts salen de su saldo on-chain) y para el pagador (abre el canal). Dejá el saldo del servicio partido en varios UTXOs, porque cada payout espera a que confirme el anterior.

```bash
lncli-pagador connect <pubkey_servicio>@127.0.0.1:<puerto>
lncli-pagador openchannel --node_key <pubkey_servicio> --local_amt 2000000
# esperar 3 confirmaciones (unos 30 min en testnet4)
```

## ln2oc

`.env` (ver `.env.testnet4.example`):

```ini
BITCOIN_NETWORK=testnet4
LND_GRPC_HOST=127.0.0.1:10009
LND_MACAROON_PATH=/ruta/lnd-servicio/data/chain/bitcoin/testnet4/admin.macaroon
LND_TLS_CERT_PATH=/ruta/lnd-servicio/tls.cert
DOMAIN=testnet.ln2oc.com
EXTERNAL_URL=https://testnet.ln2oc.com
FRONTEND_URL=https://testnet.ln2oc.com/web/   # o donde sirvas el sitio
```

Reverse proxy con TLS automático (Caddy saca el certificado de Let's Encrypt; el dominio tiene que apuntar a la máquina y los puertos 80/443 tienen que estar abiertos):

```
testnet.ln2oc.com {
    reverse_proxy 127.0.0.1:8000
}
```

`docker compose up -d --build` levanta `ln2oc` en `:8000`. Revisá en el log que diga `LND ... on testnet4`.

## Pruebas

**1. Sin wallet: el script hace lo mismo que una wallet, contra el dominio real.**

```bash
.venv/bin/python scripts/lnaddr_pay.py <tb1…>@testnet.ln2oc.com 20000 \
    --lnd-host 127.0.0.1:10010 \
    --macaroon /ruta/lnd-pagador/data/chain/bitcoin/testnet4/admin.macaroon \
    --tls-cert /ruta/lnd-pagador/tls.cert --dry-run
```

Sin `--dry-run` paga, y el payout se ve en `https://mempool.space/testnet4/address/<tb1…>`. El script chequea:

- el formato del nombre según LUD-16;
- el header CORS;
- los campos del payRequest, la metadata y el monto de la invoice;
- el `description_hash`, si la invoice lo trae.

En regtest (Polar) anda con `--allow-http` contra un uvicorn local.

**2. Con una wallet real.** No confirmé ninguna wallet móvil que pague Lightning Address en testnet4. Lo más probable es que ande ZEUS en modo remoto conectado al LND pagador (ZEUS hace la parte LNURL y paga por ese nodo), pero hay que verificar que ZEUS acepte un nodo testnet4. Si no hay wallet, el script de arriba cubre lo mismo, menos la interfaz de la wallet.

**Checklist:**

- [ ] Monto normal: invoice → pago en curso → payout en la mempool → confirmado.
- [ ] Dos pagos seguidos: el segundo queda retenido hasta que confirma el primer payout, y después sale.
- [ ] Monto debajo del mínimo y encima del máximo: error claro en la wallet.
- [ ] Saldo on-chain insuficiente: la hold invoice se cancela y el pagador no pierde nada.
- [ ] Invoice sin pagar: pasa a `EXPIRED` después de `INVOICE_EXPIRY_SECONDS`.
- [ ] Dirección legacy (`m…`/`n…`/`2…`): el servicio la rechaza con un error claro en la wallet.
- [ ] Dirección bech32 en mayúsculas: el sitio la arma en minúsculas y el servicio la guarda en minúsculas.
- [ ] Reinicio del servicio a mitad de un pago: sigue donde quedó.
- [ ] Cómo muestra la wallet un pago retenido varios minutos.
