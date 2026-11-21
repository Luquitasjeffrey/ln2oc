#!/usr/bin/env bash
# Generates Python gRPC stubs for LND from the vendored protos in proto/
# (pinned to the LND version noted in proto/LND_VERSION) into app/lnrpc/.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"
OUT=app/lnrpc
rm -rf "$OUT"
mkdir -p "$OUT"
"$PY" -m grpc_tools.protoc -I proto \
  --python_out="$OUT" --grpc_python_out="$OUT" \
  proto/lightning.proto proto/invoicesrpc/invoices.proto \
  proto/walletrpc/walletkit.proto proto/signrpc/signer.proto
# protoc emits top-level imports ("import lightning_pb2", "from signrpc import ...");
# rewrite them to be package-relative to app.lnrpc.
find "$OUT" -name '*.py' -print0 | xargs -0 sed -i -E \
  -e 's/^import (lightning_pb2)( as .*)$/from app.lnrpc import \1\2/' \
  -e 's/^from (invoicesrpc|walletrpc|signrpc) import /from app.lnrpc.\1 import /'
touch "$OUT/__init__.py" "$OUT/invoicesrpc/__init__.py" "$OUT/walletrpc/__init__.py" "$OUT/signrpc/__init__.py"
echo "Generated LND gRPC stubs in $OUT"
