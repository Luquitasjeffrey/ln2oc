#!/usr/bin/env bash
# Restores the channels of a channel.backup (SCB) after recover-wallet.sh.
# It does NOT reopen them: it asks each peer to FORCE CLOSE, and the funds arrive on-chain
# after the timelock (days). Only for disaster recovery, never with the original node alive.
source "$(dirname "$0")/common.sh"

file="${1:-}"
[[ -n "$file" && -f "$file" ]] || die "uso: $0 /ruta/al/channel.backup"
s="$(lnd_state || true)"
[[ "$s" == "SERVER_ACTIVE" ]] || die "LND tiene que estar desbloqueado y activo (estado: ${s:-SIN_RESPUESTA})"

cat <<'MSG'
ATENCIÓN: esto fuerza el cierre de TODOS los canales del backup.
Nunca lo corras si el nodo original sigue vivo con esos canales: podés perder los fondos.
MSG
read -rp "Escribí RESTAURAR para seguir: " ok
[[ "$ok" == "RESTAURAR" ]] || die "cancelado"

# The container sees LND_DIR as /lnd: copy the file there.
cp "$file" "$LND_DIR/restore-channel.backup"
trap 'rm -f "$LND_DIR/restore-channel.backup"' EXIT
lncli restorechanbackup --multi_file /lnd/restore-channel.backup
echo "Pedido enviado. Seguilo con: scripts/lnd/lncli.sh pendingchannels"
