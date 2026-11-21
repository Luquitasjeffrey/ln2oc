"""LNURL-Pay endpoints. Plain `def` handlers: FastAPI runs them in its thread pool."""
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.halt import is_halted
from app.lnd import lnd_client
from app.swaps import SwapError, create_swap
from app.validator import validate_bitcoin_address
from app.worker import swap_worker

router = APIRouter()
logger = logging.getLogger("ln2oc.lnurl")


def _error(status_code: int, reason: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "ERROR", "reason": reason})


@router.get("/.well-known/lnurlp/{btc_address}")
def lnurlp_metadata(btc_address: str):
    """
    LNURL-Pay step 1. Lightning Address: <bitcoin address>@<domain>.
    """
    if is_halted():
        return _error(503, "Service halted")
    if not validate_bitcoin_address(btc_address, settings.BITCOIN_NETWORK):
        return _error(400, f"Invalid Bitcoin address for {settings.BITCOIN_NETWORK}: {btc_address}")

    base_url = settings.EXTERNAL_URL.rstrip("/")
    callback_url = f"{base_url}/lnurlp/cb?btc_address={btc_address}"
    metadata_json = f'[["text/plain", "Swap out BTC to {btc_address}"], ["text/identifier", "{btc_address}@{settings.DOMAIN}"]]'

    return {
        "tag": "payRequest",
        "callback": callback_url,
        "minSendable": settings.MIN_SWAP_SAT * 1000,  # millisatoshis
        "maxSendable": settings.MAX_SWAP_SAT * 1000,
        "metadata": metadata_json,
        "commentAllowed": 0,
    }


@router.get("/lnurlp/cb")
def lnurlp_callback(
    amount: int = Query(..., description="Amount in millisatoshis"),
    btc_address: str = Query(..., description="Destination Bitcoin address"),
    db: Session = Depends(get_db),
):
    """LNURL-Pay step 2: issue the hold invoice."""
    if not swap_worker.can_accept_new_swaps():
        return _error(503, "Too many pending swaps, try again later")
    try:
        swap = create_swap(db=db, btc_address=btc_address, amount_msat=amount)
    except SwapError as e:
        logger.warning("Swap error for %s (%d msat): %s", btc_address, amount, e.message)
        return _error(e.status_code, e.message)
    except Exception:
        logger.exception("Unexpected error in lnurlp callback")
        return _error(500, "Internal server error")
    # Subscribe right away: the subscription is the only way the payment gets noticed.
    if not swap_worker.notify_new_swap(swap.id, bytes.fromhex(swap.payment_hash)):
        # Nobody would watch this invoice; never hand it out. Cancel it so it can't be paid
        # (on restart the worker sees it CANCELED and marks the swap EXPIRED).
        logger.error("Could not subscribe to invoice of swap %s; canceling it", swap.id)
        try:
            lnd_client.cancel_invoice(bytes.fromhex(swap.payment_hash))
        except Exception:
            logger.exception("Could not cancel unwatched invoice of swap %s", swap.id)
        return _error(503, "Too many pending swaps, try again later")
    return {"pr": swap.invoice, "routes": []}
