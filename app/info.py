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
from sqlalchemy import func, select

from app.db import SessionLocal
from app.fees import current_fee_rate_sat_per_vbyte
from app.halt import is_halted
from app.lnd import lnd_client
from app.models import Swap
from app.tx import parse_tx

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


def _last_payout_vbytes() -> int | None:
    """Per-user share of the most recent payout tx this instance signed: a real example
    of what a payout weighs here (it depends on the operator's UTXOs, the destination type
    and how many swaps the tx paid; the miner fee is split equally among them)."""
    try:
        with SessionLocal() as db:
            last = db.execute(
                select(Swap.raw_tx, Swap.txid).where(Swap.raw_tx.is_not(None)).order_by(Swap.id.desc()).limit(1)
            ).first()
            if not last:
                return None
            shared_by = db.execute(select(func.count()).where(Swap.txid == last.txid)).scalar_one()
        return -(-parse_tx(bytes.fromhex(last.raw_tx)).vsize // max(1, shared_by))
    except Exception as e:  # informational only
        logger.warning("Cannot read last payout size for /api/info: %s", e)
        return None


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
        # The miner fee is set when the payout is signed: real tx, rate of that moment.
        # These are only the current rate and the per-user size of the last real payout, as an example.
        "fee_rate_sat_vb": rate,
        "last_payout_vbytes": _last_payout_vbytes(),
        "invoice_poll_interval_seconds": settings.INVOICE_POLL_INTERVAL_SECONDS,
        "halted": is_halted(),
    }
    # Public data, read by the website from another origin. Simple GET: no preflight.
    return JSONResponse(body, headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=30"})
