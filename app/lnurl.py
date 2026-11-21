"""LNURL-Pay endpoints. Plain `def` handlers: FastAPI runs them in its thread pool."""
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.halt import is_halted
from app.swaps import SwapError, create_swap
from app.validator import ADDRESS_RULE, validate_bitcoin_address

router = APIRouter()
logger = logging.getLogger("ln2oc.lnurl")


# LUD-01: LNURL endpoints must answer with this header so browser wallets can call them.
_CORS = {"Access-Control-Allow-Origin": "*"}


def _ok(body: dict) -> JSONResponse:
    return JSONResponse(content=body, headers=_CORS)


def _error(status_code: int, reason: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "ERROR", "reason": reason}, headers=_CORS)


@router.get("/.well-known/lnurlp/{btc_address}")
def lnurlp_metadata(btc_address: str):
    """
    LNURL-Pay step 1. Lightning Address: <bitcoin address>@<domain>.
    """
    if is_halted():
        return _error(503, "Service halted")
    if not validate_bitcoin_address(btc_address, settings.BITCOIN_NETWORK):
        return _error(400, f"Invalid Bitcoin address for {settings.BITCOIN_NETWORK} ({ADDRESS_RULE}): {btc_address}")
    btc_address = btc_address.lower()  # bech32: same address; the Lightning Address name is lowercase

    base_url = settings.EXTERNAL_URL.rstrip("/")
    callback_url = f"{base_url}/lnurlp/cb?btc_address={btc_address}"
    metadata_json = f'[["text/plain", "Swap out BTC to {btc_address}"], ["text/identifier", "{btc_address}@{settings.DOMAIN}"]]'

    return _ok({
        "tag": "payRequest",
        "callback": callback_url,
        "minSendable": settings.MIN_SWAP_SAT * 1000,  # millisatoshis
        "maxSendable": settings.MAX_SWAP_SAT * 1000,
        "metadata": metadata_json,
        "commentAllowed": 0,
    })


@router.get("/lnurlp/cb")
def lnurlp_callback(
    amount: int = Query(..., description="Amount in millisatoshis"),
    btc_address: str = Query(..., description="Destination Bitcoin address"),
    db: Session = Depends(get_db),
):
    """LNURL-Pay step 2: issue the hold invoice."""
    try:
        swap = create_swap(db=db, btc_address=btc_address, amount_msat=amount)
    except SwapError as e:
        logger.warning("Swap error for %s (%d msat): %s", btc_address, amount, e.message)
        return _error(e.status_code, e.message)
    except Exception:
        logger.exception("Unexpected error in lnurlp callback")
        return _error(500, "Internal server error")
    # Nothing else to do: the worker's next poll looks up this invoice.
    return _ok({"pr": swap.invoice, "routes": []})
