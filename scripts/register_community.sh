#!/usr/bin/env bash
# Corre scripts/register_community.py (interactivo) dentro del contenedor ln2oc, contra su DB.
# Desde el checkout de la instancia (dev o prod): usa su .env y su compose.
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker compose exec -it ln2oc python -m scripts.register_community
