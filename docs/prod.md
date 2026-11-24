# Producción (piloto en mainnet)

Todo corre en una sola máquina, con el usuario del operador, en `/home/lucas/ln2oc/prod/` (checkout del repo). Los datos viven en `prod/data/` (en `.gitignore`):

```
/home/lucas/ln2oc/prod/
├── .env                 ← copia de .env.prod, completada
├── deploy/lnd/mainnet.conf
├── scripts/lnd/*.sh
└── data/
    ├── lnd/             ← LND_DIR: wallet.db, wallet_password, macaroons, tls, channel.backup
    └── ln2oc/           ← LN2OC_DATA: ln2oc.db (preimages, raw tx)
```

Servicios del compose (`COMPOSE_PROJECT_NAME=ln2oc-prod`, `COMPOSE_PROFILES=lnd`):

| Servicio | Qué es | Puertos en el host |
|---|---|---|
| `lnd` | LND v0.20.0-beta, mainnet, **neutrino** (sin blockchain local), uid 1000 | ninguno (gRPC y P2P solo en la red del compose) |
| `ln2oc` | API + worker; llega a LND por `lnd:10009` | `127.0.0.1:8100` |
| `web` | sitio estático (nginx) | `127.0.0.1:8180` |

Afuera se entra por el túnel de Cloudflare (pendiente): `/.well-known/lnurlp/`, `/lnurlp/` y `/api/` → `ln2oc:8000`; el resto → `web:8080`.

## LND

Config en `deploy/lnd/mainnet.conf`:

- `bitcoin.node=neutrino` y `fee.url`: con neutrino LND no tiene mempool, y la tasa de minería de los payouts (`EstimateFee`) sale de esa URL externa. Por eso `.env.prod` baja `MAX_SAT_PER_VBYTE` a 100.
- `tlsextradomain=lnd`: ln2oc verifica el TLS contra el nombre `lnd`.
- `wallet-unlock-password-file=/lnd/wallet_password`: se desbloquea solo en cada arranque. La contraseña queda en texto plano junto a la wallet (aceptado para el piloto).
- `wallet-unlock-allow-create`: sin wallet, LND arranca y espera. Pero el archivo de contraseña tiene que existir antes de arrancar: por eso LND lo levantan `create-wallet.sh` / `recover-wallet.sh`, después de escribirlo.
- Sin REST, sin puertos publicados. Los canales tienen que ser **públicos**: las hold invoices salen sin route hints.

## Primera vez

```bash
git clone git@github-freelance:Luquitasjeffrey/ln2oc.git /home/lucas/ln2oc/prod
cd /home/lucas/ln2oc/prod
cp .env.prod .env                  # y revisar lo marcado REVISAR / __COMPLETAR__
scripts/lnd/init-dirs.sh           # crea data/lnd y data/ln2oc con tu usuario (antes del primer up)
scripts/lnd/create-wallet.sh       # o recover-wallet.sh: escribe la contraseña y levanta LND
scripts/lnd/lncli.sh getinfo       # esperar synced_to_chain: true (neutrino: decenas de minutos)
```

Recién con LND sincronizado, fondos on-chain y un canal con liquidez entrante:

```bash
GIT_COMMIT=$(git rev-parse --short HEAD) docker compose up -d --build ln2oc web
docker compose logs -f ln2oc       # tiene que decir "LND v0.20.0-beta ... on mainnet"
```

ln2oc no arranca mientras no exista el macaroon (la wallet no está creada): falla a propósito, no se crea nada en su lugar.

## Wallet: crear, recuperar, backups

| Script | Para qué |
|---|---|
| `scripts/lnd/create-wallet.sh` | Wallet nueva. Pide la contraseña (la guarda en `data/lnd/wallet_password`) y corre `lncli create`: misma contraseña, `n`, passphrase del seed opcional. **Las 24 palabras, en papel.** Al final reinicia LND y verifica que se desbloquee solo. |
| `scripts/lnd/recover-wallet.sh` | Recuperar desde las 24 palabras + la passphrase del seed (si tenía). Mismo flujo, respondiendo `y`. Recupera lo on-chain (reescaneo con neutrino, puede tardar). |
| `scripts/lnd/restore-channels.sh <channel.backup>` | Después de recuperar: pide a los peers que **fuercen el cierre** de los canales del SCB. Los fondos llegan on-chain tras el timelock. Nunca con el nodo original vivo. |
| `scripts/lnd/backup-scb.sh <dir>` | Copia `channel.backup` con fecha. Correrlo después de abrir o cerrar un canal (o por cron), a otro disco. |
| `scripts/lnd/lncli.sh ...` | `lncli` contra el LND del compose (`getinfo`, `walletbalance`, `newaddress p2tr`, `openchannel`...). |

Los scripts nunca pisan una wallet existente: si `wallet.db` ya está, frenan.

**Qué guardar fuera de la máquina:** las 24 palabras + la passphrase del seed (papel), `channel.backup` (después de cada cambio de canales) y `data/ln2oc/ln2oc.db` (preimages y raw tx: sin eso no se puede reconstruir qué se le debe a quién).

## Recuperación en una máquina nueva

```bash
git clone ... /home/lucas/ln2oc/prod && cd /home/lucas/ln2oc/prod
cp .env.prod .env && scripts/lnd/init-dirs.sh
scripts/lnd/recover-wallet.sh
scripts/lnd/restore-channels.sh /ruta/channel.backup     # si había canales
# copiar la ln2oc.db del backup a data/ln2oc/ antes de levantar ln2oc
```

## Pendiente para salir

- Túnel de Cloudflare + DNS (ruteo por path, Bot Fight Mode apagado en las rutas LNURL).
- Fondos on-chain al nodo, canal público y liquidez entrante.
- Ajustar `MAX_SWAP_SAT` a la liquidez real.
- Macaroon con permisos mínimos (TODO 3), monitor externo de `/api/info`, cron de backup.
