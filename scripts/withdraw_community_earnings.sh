#!/usr/bin/env bash
# Corre scripts/withdraw_community_earnings.py (interactivo) dentro del contenedor ln2oc, contra su DB.
# Desde el checkout de la instancia (dev o prod): usa su .env y su compose.
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker compose exec -it ln2oc python -m scripts.withdraw_community_earnings
