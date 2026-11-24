# Shared by scripts/lnd/*.sh. Source it, do not run it.
# Reads the instance config from .env (without executing it) and gives lncli/compose helpers.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

die() { echo "ERROR: $*" >&2; exit 1; }

# env_get KEY DEFAULT: value of KEY in .env (last one wins), or DEFAULT.
env_get() {
    local v=""
    if [[ -f .env ]]; then
        v="$(grep -E "^[[:space:]]*$1=" .env | tail -n1 | sed -E "s/^[[:space:]]*$1=//; s/^[\"']//; s/[\"']$//" || true)"
    fi
    echo "${v:-$2}"
}

[[ -f .env ]] || die "no hay .env en $REPO_DIR (copiá .env.prod o .env.dev)"

NETWORK="$(env_get BITCOIN_NETWORK regtest)"
LND_DIR="$(env_get LND_DIR ./data/lnd)"
[[ "$LND_DIR" = /* ]] || LND_DIR="$REPO_DIR/${LND_DIR#./}"
WALLET_DB="$LND_DIR/data/chain/bitcoin/$NETWORK/wallet.db"
PASSWORD_FILE="$LND_DIR/wallet_password"

grep -qE '^[[:space:]]*COMPOSE_PROFILES=.*lnd' .env \
    || die "este .env no usa el LND del compose (falta COMPOSE_PROFILES=lnd)"

# lncli inside the lnd container (gRPC is not published on the host).
lncli() {
    local tty=()
    [[ -t 0 && -t 1 ]] || tty=(-T)
    docker compose exec "${tty[@]}" lnd lncli --lnddir=/lnd --network="$NETWORK" --rpcserver=localhost:10009 "$@"
}

lnd_running() {
    [[ -n "$(docker compose ps -q --status running lnd 2>/dev/null)" ]]
}

# lnd_state: NON_EXISTING, LOCKED, UNLOCKED, RPC_ACTIVE, SERVER_ACTIVE, WAITING_TO_START...
lnd_state() {
    lncli state 2>/dev/null | sed -nE 's/.*"state": *"([A-Z_]+)".*/\1/p'
}

# wait_state STATE...: waits up to 2 min until LND reports one of the given states.
wait_state() {
    local s=""
    for _ in $(seq 60); do
        s="$(lnd_state || true)"
        for want in "$@"; do [[ "$s" == "$want" ]] && { echo "$s"; return 0; }; done
        sleep 2
    done
    echo "${s:-SIN_RESPUESTA}"
    return 1
}

# ask_password: reads the wallet password twice into WALLET_PASSWORD.
ask_password() {
    local p1 p2
    read -rsp "Contraseña de la wallet LND (mín. 8 caracteres): " p1; echo
    read -rsp "Repetila: " p2; echo
    [[ "$p1" == "$p2" ]] || die "las contraseñas no coinciden"
    [[ ${#p1} -ge 8 ]] || die "la contraseña tiene que tener al menos 8 caracteres"
    WALLET_PASSWORD="$p1"
}

# write_password_file: LND reads it at every start to unlock the wallet by itself.
write_password_file() {
    local tmp
    tmp="$(mktemp "$LND_DIR/.wallet_password.XXXXXX")"
    chmod 600 "$tmp"
    printf '%s' "$WALLET_PASSWORD" > "$tmp"
    mv "$tmp" "$PASSWORD_FILE"
}

# preflight_new_wallet: no wallet yet. Never overwrites an existing wallet.
preflight_new_wallet() {
    [[ ! -e "$WALLET_DB" ]] || die "ya existe una wallet en $WALLET_DB. No piso nada: si de verdad querés empezar de cero, movela vos a mano (con LND parado)."
    [[ -d "$LND_DIR" ]] || die "no existe $LND_DIR: corré scripts/lnd/init-dirs.sh"
}

# start_lnd_without_wallet: LND refuses to start until the password file exists, so it is
# (re)started here, after write_password_file, and must come up waiting for a wallet.
start_lnd_without_wallet() {
    docker compose up -d --force-recreate lnd >/dev/null
    local s
    s="$(wait_state NON_EXISTING LOCKED UNLOCKED RPC_ACTIVE SERVER_ACTIVE)" || die "LND no responde (estado: $s). Mirá: docker compose logs --tail 50 lnd"
    [[ "$s" == "NON_EXISTING" ]] || die "LND dice que ya hay una wallet (estado: $s)"
}

# verify_auto_unlock: restarts LND and checks it unlocks alone with the password file.
verify_auto_unlock() {
    echo
    echo "Reiniciando LND para verificar que se desbloquea solo con $PASSWORD_FILE ..."
    docker compose restart lnd >/dev/null
    local s
    if s="$(wait_state RPC_ACTIVE SERVER_ACTIVE)"; then
        echo "OK: LND se desbloqueó solo (estado: $s)."
    else
        die "LND no se desbloqueó solo (estado: $s). ¿Escribiste en lncli la misma contraseña que acá? Corregí $PASSWORD_FILE (chmod 600) y reiniciá: docker compose restart lnd"
    fi
}
