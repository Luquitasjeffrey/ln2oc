#!/usr/bin/env bash
# Creates a NEW LND wallet (new seed). For an existing seed: recover-wallet.sh.
#
# 1. Asks for the wallet password and saves it in $LND_DIR/wallet_password (auto unlock).
# 2. Runs `lncli create`: type THE SAME password, answer "n" (new seed) and, if you want,
#    a seed passphrase (aezeed). Without that passphrase the seed alone can't recover the wallet.
# 3. Write the 24 words on paper. They are shown only once, only in this terminal.
# 4. Restarts LND and checks that it unlocks alone.
source "$(dirname "$0")/common.sh"

preflight_new_wallet

cat <<MSG
Red: $NETWORK
Primero la contraseña con la que LND cifra la wallet (queda en $PASSWORD_FILE para el
desbloqueo automático). Después lncli te la pide de nuevo: escribí LA MISMA.
MSG
ask_password
write_password_file
unset WALLET_PASSWORD

cat <<'MSG'

Ahora lncli create:
  - contraseña: la misma de recién (dos veces)
  - "existing cipher seed ... (Enter y/x/n)": n
  - passphrase del seed: opcional. Si ponés una, sin ella las 24 palabras no alcanzan
  - anotá las 24 palabras EN PAPEL. No las copies a ningún archivo ni chat

MSG
lncli create

verify_auto_unlock
echo
echo "Listo. LND empieza a sincronizar neutrino; seguilo con: scripts/lnd/lncli.sh getinfo (synced_to_chain)"
