"""
Integration fixtures against a Polar regtest network:
  - polar-n3-Kross: runs the swap service (gRPC 127.0.0.1:10001)
  - polar-n3-User:  the payer (gRPC 127.0.0.1:10002)
  - polar-n3-backend1: bitcoind (mining, tx inspection)
"""
import concurrent.futures
import hashlib
import json
import os
import subprocess
import time

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.lnd import LndClient, lnd_client
from app.lnrpc import lightning_pb2 as ln
from app.main import app
from app.models import Swap, SwapStatus
from app.worker import SwapWorker

BITCOIND_CONTAINER = "polar-n3-backend1"
RPC_USER = "polaruser"
RPC_PASS = "polarpass"

USER_LND_HOST = "127.0.0.1:10002"
USER_MACAROON_PATH = "/home/lucas/.polar/networks/3/volumes/lnd/User/data/chain/bitcoin/regtest/admin.macaroon"
USER_TLS_CERT_PATH = "/home/lucas/.polar/networks/3/volumes/lnd/User/tls.cert"


def bitcoin_cli(*args: str) -> str:
    cmd = ["docker", "exec", BITCOIND_CONTAINER, "bitcoin-cli", "-regtest",
           f"-rpcuser={RPC_USER}", f"-rpcpassword={RPC_PASS}", *args]
    return subprocess.check_output(cmd, text=True).strip()


def mine_blocks(num_blocks: int = 1) -> None:
    addr = bitcoin_cli("getnewaddress")
    bitcoin_cli("generatetoaddress", str(num_blocks), addr)
    # Let LND catch up so synced_to_chain is true again.
    for _ in range(50):
        info = lnd_client.get_info()
        if info.synced_to_chain and int(info.block_height) == int(bitcoin_cli("getblockcount")):
            return
        time.sleep(0.2)
    raise RuntimeError("LND did not sync after mining")


def new_dest_address() -> str:
    return bitcoin_cli("getnewaddress", "", "bech32")


def get_bitcoind_tx(txid: str) -> dict:
    return json.loads(bitcoin_cli("getrawtransaction", txid, "1"))


def received_by(address: str, minconf: int = 0) -> int:
    """Total sats ever received by a bitcoind wallet address."""
    btc = bitcoin_cli("getreceivedbyaddress", address, str(minconf))
    return int(round(float(btc) * 100_000_000))


class Payer:
    """Pays invoices from the User node in the background (hold invoices block the sender)."""

    def __init__(self):
        self.lnd = LndClient(host=USER_LND_HOST, macaroon_path=USER_MACAROON_PATH, tls_cert_path=USER_TLS_CERT_PATH)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    def pay(self, payment_request: str) -> concurrent.futures.Future:
        stub, _, _ = self.lnd._stubs()
        return self.pool.submit(
            lambda: stub.SendPaymentSync(ln.SendRequest(payment_request=payment_request), timeout=120)
        )


@pytest.fixture(scope="session")
def payer():
    p = Payer()
    yield p
    p.pool.shutdown(wait=False, cancel_futures=True)


class FatalRecorder:
    def __init__(self):
        self.reasons: list[str] = []

    def __call__(self, reason: str):
        self.reasons.append(reason)


@pytest.fixture
def env(tmp_path):
    """Fresh SQLite DB + a worker bound to it whose 'halt' only records the reason."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}, future=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    Base.metadata.create_all(bind=engine)
    fatal = FatalRecorder()
    worker = SwapWorker(session_factory=Session, retry_interval_seconds=0.2,
                        lock_path=str(tmp_path / "worker.lock"), on_fatal=fatal)
    e = {"Session": Session, "worker": worker, "fatal": fatal, "tmp_path": tmp_path}
    yield e
    for w in {id(worker): worker, id(e["worker"]): e["worker"]}.values():
        w.stop() if w._running else w.release_process_lock()
    engine.dispose()


@pytest_asyncio.fixture
async def client(env):
    def override_get_db():
        db = env["Session"]()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)  # does not run the lifespan (no global worker)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


def insert_swap(Session, amount_sat: int, payout_sat: int, miner_fee_sat: int, address: str,
                fee_rate_sat_vb: int | None = None) -> tuple[int, str]:
    """Creates a real hold invoice in Kross and a PENDING swap row, bypassing create_swap checks."""
    if fee_rate_sat_vb is None:
        from app.fees import current_fee_rate_sat_per_vbyte
        fee_rate_sat_vb = current_fee_rate_sat_per_vbyte(lnd_client)
    preimage = os.urandom(32)
    payment_hash = hashlib.sha256(preimage).digest()
    resp = lnd_client.add_hold_invoice(
        payment_hash=payment_hash, value_sat=amount_sat, memo="ln2oc test",
        expiry_seconds=600, cltv_expiry=settings.HOLD_INVOICE_CLTV_EXPIRY,
    )
    with Session() as db:
        swap = Swap(
            payment_hash=payment_hash.hex(), preimage=preimage.hex(), btc_address=address,
            amount_sat=amount_sat, payout_sat=payout_sat, miner_fee_sat=miner_fee_sat,
            fee_rate_sat_vb=fee_rate_sat_vb, invoice=resp.payment_request, lock_id=os.urandom(32).hex(), status=SwapStatus.PENDING,
        )
        db.add(swap)
        db.commit()
        return swap.id, resp.payment_request


def get_swap(Session, swap_id: int) -> Swap:
    with Session() as db:
        swap = db.get(Swap, swap_id)
        db.expunge(swap)
        return swap


def tick_until(env, swap_id: int, statuses, max_ticks: int = 60) -> Swap:
    """Drives a non-running worker by hand: every tick is a full poll of the PENDING
    invoices (the worker thread's two paces are tested separately)."""
    statuses = set(statuses)
    for _ in range(max_ticks):
        env["worker"].run_tick_guarded()
        swap = get_swap(env["Session"], swap_id)
        if swap.status in statuses or env["fatal"].reasons:
            return swap
        time.sleep(0.25)
    return get_swap(env["Session"], swap_id)


def leases_for(lock_id_hex: str) -> list:
    lock_id = bytes.fromhex(lock_id_hex)
    return [l for l in lnd_client.list_leases() if l.id == lock_id]


def wait_for_status(Session, swap_id: int, statuses, timeout: float = 30.0) -> Swap:
    """Waits (without ticking) for a running worker to move a swap."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        swap = get_swap(Session, swap_id)
        if swap.status in set(statuses):
            return swap
        time.sleep(0.1)
    return get_swap(Session, swap_id)
