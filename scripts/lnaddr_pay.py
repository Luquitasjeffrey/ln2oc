#!/usr/bin/env python3
"""
Pays a Lightning Address the way a wallet does (LUD-16 + LUD-06), from an LND node you
control. For testing a real deployment (domain, HTTPS, reverse proxy, the service and its
worker) end to end, e.g. on testnet4, without depending on a mobile wallet.

  .venv/bin/python scripts/lnaddr_pay.py <address>@<domain> <sats> \
      --lnd-host 127.0.0.1:10009 --macaroon ~/.lnd/.../admin.macaroon --tls-cert ~/.lnd/tls.cert

Steps (each check is what some wallet does; a failure stops before paying):
  1. LUD-16: the name is lowercase a-z0-9-_. ; GET https://<domain>/.well-known/lnurlp/<name>
  2. LUD-06: payRequest fields, amount within min/max, metadata with one text/plain and a
     text/identifier matching the address; LUD-01: Access-Control-Allow-Origin header
  3. GET <callback>&amount=<msat>; decode the invoice with the payer's LND: amount equals
     the requested one, network matches; if it carries a description_hash it must be
     sha256(metadata) (ZEUS rejects a mismatch)
  4. Pay (unless --dry-run). With a hold invoice this blocks until the service settles.

Needs the generated stubs (scripts/gen_protos.sh). Uses only the stdlib for HTTP.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import grpc  # noqa: E402

from app.lnrpc import lightning_pb2 as ln  # noqa: E402
from app.lnrpc import lightning_pb2_grpc as ln_grpc  # noqa: E402

LUD16_NAME = re.compile(r"^[a-z0-9\-_.]+$")


class Fail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise Fail(msg)
    print(f"  ok  {msg}")


def warn(msg: str) -> None:
    print(f"  !!  {msg}")


def get_json(url: str, allow_http: bool):
    scheme = urllib.parse.urlsplit(url).scheme
    if scheme != "https" and not allow_http:
        raise Fail(f"{url}: wallets only accept https (or http on .onion); use --allow-http for local tests")
    req = urllib.request.Request(url, headers={"User-Agent": "ln2oc-lnaddr-test", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, headers, raw = resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:  # LUD-01: status codes carry no meaning, read the body
        status, headers, raw = e.code, e.headers, e.read()
    try:
        body = json.loads(raw)
    except ValueError:
        raise Fail(f"{url}: HTTP {status}, body is not JSON: {raw[:200]!r}")
    if status != 200:
        warn(f"{url}: HTTP {status} (LUD-01 says it has no meaning, but some wallets only read 200 bodies)")
    if headers.get("Access-Control-Allow-Origin") != "*":
        warn(f"{url}: no 'Access-Control-Allow-Origin: *' (LUD-01): browser wallets cannot call it")
    if isinstance(body, dict) and body.get("status") == "ERROR":
        raise Fail(f"{url}: service error: {body.get('reason')}")
    return body


def lnd_stub(host: str, macaroon: str, tls_cert: str):
    with open(os.path.expanduser(tls_cert), "rb") as f:
        cert = f.read()
    with open(os.path.expanduser(macaroon), "rb") as f:
        mac = f.read().hex()
    creds = grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(root_certificates=cert),
        grpc.metadata_call_credentials(lambda _ctx, cb: cb((("macaroon", mac),), None)),
    )
    return ln_grpc.LightningStub(grpc.secure_channel(host, creds))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("address", help="<bitcoin address>@<domain>")
    ap.add_argument("sats", type=int)
    ap.add_argument("--lnd-host", required=True, help="payer LND gRPC host:port")
    ap.add_argument("--macaroon", required=True, help="payer LND macaroon (needs offchain read/write)")
    ap.add_argument("--tls-cert", required=True, help="payer LND tls.cert")
    ap.add_argument("--dry-run", action="store_true", help="do every check but do not pay")
    ap.add_argument("--allow-http", action="store_true", help="allow http:// (local tests only)")
    ap.add_argument("--timeout", type=int, default=7200, help="seconds to wait for the payment (hold invoice)")
    a = ap.parse_args()

    try:
        name, _, domain = a.address.partition("@")
        print("1. Lightning Address (LUD-16)")
        check(bool(name) and bool(domain), f"{a.address} has the form name@domain")
        check(bool(LUD16_NAME.match(name)), f"name is lowercase a-z0-9-_. ({len(name)} chars)")
        scheme = "http" if a.allow_http else "https"
        pay_request = get_json(f"{scheme}://{domain}/.well-known/lnurlp/{name}", a.allow_http)

        print("2. payRequest (LUD-06)")
        check(pay_request.get("tag") == "payRequest", "tag is payRequest")
        lo, hi = pay_request.get("minSendable"), pay_request.get("maxSendable")
        check(isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi, f"minSendable {lo} <= maxSendable {hi} msat")
        amount_msat = a.sats * 1000
        check(lo <= amount_msat <= hi, f"{a.sats} sat is within [{lo // 1000}, {hi // 1000}] sat")
        metadata_raw = pay_request.get("metadata")
        check(isinstance(metadata_raw, str), "metadata is a raw string")
        metadata = json.loads(metadata_raw)
        plain = [v for k, v in metadata if k == "text/plain"]
        check(len(plain) == 1, f"exactly one text/plain: {plain[0] if plain else None!r}")
        ids = [v for k, v in metadata if k in ("text/identifier", "text/email")]
        check(len(ids) == 1, f"one text/identifier or text/email: {ids}")
        if ids[0] != a.address:
            warn(f"identifier {ids[0]!r} != {a.address!r} (no wallet is required to check it)")
        callback = pay_request.get("callback", "")
        check(urllib.parse.urlsplit(callback).netloc == domain or a.allow_http,
              f"callback on the same host: {callback}")

        print("3. Invoice")
        sep = "&" if "?" in callback else "?"
        res = get_json(f"{callback}{sep}amount={amount_msat}", a.allow_http)
        pr = res.get("pr")
        check(isinstance(pr, str) and pr.startswith("ln"), f"pr: {pr[:40] if pr else pr}...")
        stub = lnd_stub(a.lnd_host, a.macaroon, a.tls_cert)
        info = stub.GetInfo(ln.GetInfoRequest(), timeout=30)
        decoded = stub.DecodePayReq(ln.PayReqString(pay_req=pr), timeout=30)  # fails on another network
        check(decoded.num_msat == amount_msat, f"invoice amount {decoded.num_msat} msat == requested")
        if decoded.description_hash:
            check(decoded.description_hash == hashlib.sha256(metadata_raw.encode()).hexdigest(),
                  "description_hash == sha256(metadata)")
        else:
            print(f"  --  no description_hash (LUD-06 no longer requires it); memo: {decoded.description!r}")
        print(f"      destination {decoded.destination}, expiry {decoded.expiry}s, final CLTV {decoded.cltv_expiry}")
        print(f"      payer node {info.alias or info.identity_pubkey[:16]} on {[c.network for c in info.chains]}")

        if a.dry_run:
            print("Dry run: not paying.")
            return 0
        print(f"4. Paying {a.sats} sat (a hold invoice blocks until the service settles; up to {a.timeout}s)...")
        resp = stub.SendPaymentSync(ln.SendRequest(payment_request=pr), timeout=a.timeout)
        if resp.payment_error:
            raise Fail(f"payment failed: {resp.payment_error}")
        print(f"  ok  paid, preimage {resp.payment_preimage.hex()}")
        print(f"Now check the payout to {name} in a block explorer (it is broadcast right after the settle).")
        return 0
    except Fail as e:
        print(f"FAIL {e}")
        return 1
    except grpc.RpcError as e:
        print(f"FAIL LND: {e.code().name}: {e.details()}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
