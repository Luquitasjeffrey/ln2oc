import os
import subprocess
import pytest
import pytest_asyncio
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, get_db
from app.main import app
from app.lnd import LndClient
from app.worker import SwapWorker

BITCOIND_CONTAINER = "polar-n3-backend1"
RPC_USER = "polaruser"
RPC_PASS = "polarpass"

USER_LND_HOST = "127.0.0.1:8082"
USER_MACAROON_PATH = "/home/lucas/.polar/networks/3/volumes/lnd/User/data/chain/bitcoin/regtest/admin.macaroon"
USER_TLS_CERT_PATH = "/home/lucas/.polar/networks/3/volumes/lnd/User/tls.cert"

def mine_blocks(num_blocks: int = 1) -> str:
    """Mines blocks to a new address on polar-n3-backend1."""
    # 1. Get new address
    cmd_addr = [
        "docker", "exec", BITCOIND_CONTAINER,
        "bitcoin-cli", "-regtest", f"-rpcuser={RPC_USER}", f"-rpcpassword={RPC_PASS}",
        "getnewaddress"
    ]
    addr = subprocess.check_output(cmd_addr, text=True).strip()

    # 2. Generate blocks
    cmd_mine = [
        "docker", "exec", BITCOIND_CONTAINER,
        "bitcoin-cli", "-regtest", f"-rpcuser={RPC_USER}", f"-rpcpassword={RPC_PASS}",
        "generatetoaddress", str(num_blocks), addr
    ]
    return subprocess.check_output(cmd_mine, text=True).strip()

def get_bitcoind_tx(txid: str) -> dict:
    """Retrieves raw transaction info from bitcoind."""
    cmd = [
        "docker", "exec", BITCOIND_CONTAINER,
        "bitcoin-cli", "-regtest", f"-rpcuser={RPC_USER}", f"-rpcpassword={RPC_PASS}",
        "getrawtransaction", txid, "1"
    ]
    import json
    out = subprocess.check_output(cmd, text=True).strip()
    return json.loads(out)

@pytest.fixture(scope="session")
def user_lnd():
    return LndClient(
        host=USER_LND_HOST,
        macaroon_path=USER_MACAROON_PATH,
        tls_cert_path=USER_TLS_CERT_PATH,
    )

@pytest_asyncio.fixture
async def test_app():
    # Use an in-memory SQLite database or test file for clean tests
    test_db_file = "./test_swapservice.db"
    if os.path.exists(test_db_file):
        os.remove(test_db_file)

    test_engine = create_engine(
        f"sqlite:///{test_db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine, future=True)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Initialize a custom worker pointing to test db
    test_worker = SwapWorker(poll_interval_seconds=0.5)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {
            "client": client,
            "session_factory": TestingSessionLocal,
            "worker": test_worker,
        }

    app.dependency_overrides.clear()
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
