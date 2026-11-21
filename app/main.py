import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.config import APP_VERSION, settings
from app.db import SessionLocal, init_db, verify_schema
from app.lnd import lnd_client
from app.info import router as info_router
from app.lnurl import router as lnurl_router
from app.models import Swap, SwapStatus
from app.worker import swap_worker

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s (%(threadName)s): %(message)s",
)
logger = logging.getLogger("ln2oc")

# BITCOIN_NETWORK -> what LND's GetInfo reports in chains[].network (lncfg.NormalizeNetwork:
# testnet3 is reported as "testnet", testnet4 as "testnet4").
_LND_NETWORK = {"mainnet": "mainnet", "testnet": "testnet", "testnet4": "testnet4", "regtest": "regtest"}


def startup_checks() -> None:
    """Every check here refuses to start the service rather than run in a bad state."""
    init_db()
    verify_schema()

    with SessionLocal() as db:
        review = list(db.execute(select(Swap).where(Swap.status == SwapStatus.MANUAL_REVIEW)).scalars())
    if review:
        details = "; ".join(f"swap {s.id}: {s.error}" for s in review)
        raise RuntimeError(f"{len(review)} swap(s) in MANUAL_REVIEW, resolve them before starting: {details}")

    info = lnd_client.get_info()
    networks = {(c.chain, c.network) for c in info.chains}
    expected = ("bitcoin", _LND_NETWORK[settings.BITCOIN_NETWORK.lower()])
    if networks != {expected}:
        raise RuntimeError(f"LND is on {networks}, but BITCOIN_NETWORK={settings.BITCOIN_NETWORK}")
    logger.info("LND %s on %s, block %d, synced=%s", info.version, expected[1], info.block_height, info.synced_to_chain)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lock first: a second process must not even run the checks concurrently.
    swap_worker.acquire_process_lock()
    try:
        startup_checks()
        swap_worker.start()
    except Exception:
        swap_worker.release_process_lock()
        raise
    yield
    swap_worker.stop()


app = FastAPI(
    title="ln2oc - Lightning to On-Chain Swap Service",
    description="Minimal Lightning Address to Bitcoin on-chain swap-out service.",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.include_router(lnurl_router)
app.include_router(info_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
