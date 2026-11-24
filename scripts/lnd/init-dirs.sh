#!/usr/bin/env bash
# Creates the data directories of the instance, owned by the current user, BEFORE the
# first `docker compose up` (if docker creates them, they end up owned by root and
# neither LND nor ln2oc can write).
source "$(dirname "$0")/common.sh"

[[ "$(id -u)" == "$(env_get APP_UID 1000)" ]] || die "corré esto con el usuario de APP_UID ($(env_get APP_UID 1000))"

mkdir -p "$LND_DIR"
chmod 700 "$LND_DIR"
echo "LND:   $LND_DIR"

data="$(env_get LN2OC_DATA "")"
if [[ "$data" == /* || "$data" == ./* ]]; then
    [[ "$data" = /* ]] || data="$REPO_DIR/${data#./}"
    mkdir -p "$data"
    chmod 700 "$data"
    echo "ln2oc: $data"
fi
