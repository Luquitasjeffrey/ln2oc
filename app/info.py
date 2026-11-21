"""Public, read-only endpoints that are not LNURL: the redirect of `/` to the website
and `/api/info` with this instance's parameters.

The website (web/) is served by its own server. FastAPI never serves frontend files:
it only redirects `/` there."""
import logging
import subprocess
import threading
import time
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import APP_VERSION, settings
from app.fees import ESTIMATED_TX_VBYTES, calculate_miner_fee, current_fee_rate_sat_per_vbyte
from app.halt import is_halted
from app.lnd import lnd_client

router = APIRouter()
logger = logging.getLogger("ln2oc.info")

# /api/info is public: cache the fee estimate so requests to it never hammer LND.
_FEE_CACHE_SECONDS = 30.0
_fee_lock = threading.Lock()
_fee_cache: tuple[float, int | None] = (0.0, None)


@lru_cache(maxsize=1)
def git_commit() -> str:
    """Commit this instance runs: GIT_COMMIT (set at docker build), else the checkout's HEAD."""
    if settings.GIT_COMMIT:
        return settings.GIT_COMMIT[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"], cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=2, check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _fee_rate_sat_vb() -> int | None:
    global _fee_cache
    with _fee_lock:
        fetched_at, rate = _fee_cache
        if time.monotonic() - fetched_at < _FEE_CACHE_SECONDS:
            return rate
        try:
            rate = current_fee_rate_sat_per_vbyte(lnd_client)
        except Exception as e:  # informational only: the callback re-estimates and refuses
            logger.warning("Fee estimate unavailable for /api/info: %s", e)
            rate = None
        _fee_cache = (time.monotonic(), rate)
        return rate


@router.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root():
    if not settings.FRONTEND_URL:
        return Response(status_code=404)
    return RedirectResponse(settings.FRONTEND_URL, status_code=302)


@router.get("/api/info")
def info():
    rate = _fee_rate_sat_vb()
    body = {
        "service": "ln2oc",
        "version": APP_VERSION,
        "commit": git_commit(),
        "network": settings.BITCOIN_NETWORK.lower(),
        "domain": settings.DOMAIN,
        "swap_fee_rate_bps": int(round(settings.SWAP_FEE_RATE * 10_000)),
        "min_swap_sat": settings.MIN_SWAP_SAT,
        "max_swap_sat": settings.MAX_SWAP_SAT,
        "min_payout_sat": settings.MIN_PAYOUT_SAT,
        "estimated_tx_vbytes": ESTIMATED_TX_VBYTES,
        "fee_rate_sat_vb": rate,
        "miner_fee_sat": calculate_miner_fee(rate) if rate is not None else None,
        "invoice_poll_interval_seconds": settings.INVOICE_POLL_INTERVAL_SECONDS,
        "halted": is_halted(),
    }
    # Public data, read by the website from another origin. Simple GET: no preflight.
    return JSONResponse(body, headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=30"})
