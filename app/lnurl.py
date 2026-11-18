import logging
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.validator import validate_bitcoin_address
from app.config import settings
from app.swaps import create_swap, SwapError

router = APIRouter()
logger = logging.getLogger("ln2oc.lnurl")

@router.get("/.well-known/lnurlp/{btc_address}")
async def lnurlp_metadata(btc_address: str, request: Request):
    """
    LNURL-Pay Step 1:
    Accepts Lightning Address requests like: bc1q...@swapservice.com
    Where username is the Bitcoin destination address.
    """
    if not validate_bitcoin_address(btc_address, settings.BITCOIN_NETWORK):
        return JSONResponse(
            status_code=400,
            content={"status": "ERROR", "reason": f"Invalid Bitcoin address for {settings.BITCOIN_NETWORK}: {btc_address}"}
        )

    base_url = settings.EXTERNAL_URL.rstrip("/")
    callback_url = f"{base_url}/lnurlp/cb?btc_address={btc_address}"
    metadata_json = f'[["text/plain", "Swap out BTC to {btc_address}"], ["text/identifier", "{btc_address}@{settings.DOMAIN}"]]'

    return {
        "tag": "payRequest",
        "callback": callback_url,
        "minSendable": settings.MIN_SWAP_SAT * 1000,  # in millisatoshis
        "maxSendable": settings.MAX_SWAP_SAT * 1000,  # in millisatoshis
        "metadata": metadata_json,
        "commentAllowed": 0,
    }

@router.get("/lnurlp/cb")
async def lnurlp_callback(
    request: Request,
    amount: int = Query(..., description="Amount in millisatoshis"),
    btc_address: str = Query(None, description="BTC address if passed as param"),
    db: Session = Depends(get_db),
):
    """
    LNURL-Pay Step 2:
    Receives callback request with amount in millisatoshis.
    If btc_address is not a query param, we can extract from referer or query params.
    Wait, LNURL-Pay spec: The callback URL returned in Step 1 can include query params!
    Let's check how Step 1 formats the callback URL or handle query params.
    """
    # If btc_address is in query params (which we provide in callback)
    if not btc_address:
        # Check query string directly
        params = dict(request.query_params)
        btc_address = params.get("btc_address")

    if not btc_address:
        return JSONResponse(
            status_code=400,
            content={"status": "ERROR", "reason": "Missing btc_address parameter in callback."}
        )

    try:
        swap = await create_swap(db=db, btc_address=btc_address, amount_msat=amount)
        return {
            "pr": swap.invoice,
            "routes": [],
        }
    except SwapError as e:
        logger.warning("Swap error for %s (%d msat): %s", btc_address, amount, e.message)
        return JSONResponse(
            status_code=e.status_code,
            content={"status": "ERROR", "reason": e.message}
        )
    except Exception as e:
        logger.exception("Unexpected error in lnurlp callback: %s", e)
        return JSONResponse(
            status_code=500,
            content={"status": "ERROR", "reason": "Internal server error"}
        )
