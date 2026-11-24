#!/usr/bin/env bash
# lncli against the LND of the compose. E.g.: scripts/lnd/lncli.sh getinfo
source "$(dirname "$0")/common.sh"
lncli "$@"
