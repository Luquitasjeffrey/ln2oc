#!/usr/bin/env bash
# Copies LND's Static Channel Backup (channel.backup) to DEST_DIR with a timestamp.
# LND rewrites it every time a channel opens or closes: run it after every change (or by cron).
# Without the SCB, the seed recovers the on-chain funds but NOT the channel funds.
source "$(dirname "$0")/common.sh"

dest="${1:-}"
[[ -n "$dest" ]] || die "uso: $0 DEST_DIR (idealmente fuera de esta máquina o en otro disco)"
src="$LND_DIR/data/chain/bitcoin/$NETWORK/channel.backup"
[[ -f "$src" ]] || die "no existe $src (¿la wallet ya está creada?)"
mkdir -p "$dest"
out="$dest/channel.backup.$NETWORK.$(date -u +%Y%m%dT%H%M%SZ)"
cp "$src" "$out"
chmod 600 "$out"
echo "$out"
