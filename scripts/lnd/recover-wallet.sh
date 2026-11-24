#!/usr/bin/env bash
# Recovers the LND wallet from the 24 words (aezeed) and, if it had one, its passphrase.
# Recovers the ON-CHAIN funds. Channel funds come back with restore-channels.sh and the
# SCB (channel.backup): that force-closes every channel.
#
# Needs an LND without wallet: on a fresh machine, init-dirs.sh + `docker compose up -d lnd`.
source "$(dirname "$0")/common.sh"

preflight_new_wallet

cat <<MSG
Red: $NETWORK
Primero la contraseña NUEVA con la que LND va a cifrar la wallet (puede ser otra que la
original; queda en $PASSWORD_FILE para el desbloqueo automático). Después lncli te la pide
de nuevo: escribí LA MISMA.
MSG
ask_password
write_password_file
unset WALLET_PASSWORD

cat <<'MSG'

Ahora lncli create:
  - contraseña: la misma de recién (dos veces)
  - "existing cipher seed ... (Enter y/x/n)": y
  - las 24 palabras separadas por espacios
  - la passphrase del seed (Enter si no tenía)
  - "address look-ahead": Enter (2500) alcanza para este nodo

MSG
lncli create

verify_auto_unlock
cat <<'MSG'

Listo. LND reescanea la cadena con neutrino para encontrar los fondos on-chain: puede tardar.
Seguilo con: scripts/lnd/lncli.sh getinfo   y   scripts/lnd/lncli.sh walletbalance
Si el nodo tenía canales: scripts/lnd/restore-channels.sh <channel.backup>
MSG
