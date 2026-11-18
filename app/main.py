import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import init_db
from app.lnurl import router as lnurl_router
from app.worker import swap_worker
from app.config import settings

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ln2oc")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    init_db()
    logger.info("Starting background swap worker...")
    await swap_worker.start()
    yield
    # Shutdown
    logger.info("Stopping background swap worker...")
    await swap_worker.stop()

app = FastAPI(
    title="ln2oc - Lightning to On-Chain Swap Service",
    description="Minimal Lightning Address to Bitcoin on-chain swap-out service.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(lnurl_router)

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
