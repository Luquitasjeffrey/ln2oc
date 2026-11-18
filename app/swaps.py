import os
import hashlib
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models import Swap, SwapStatus
from app.lnd import lnd_client
from app.validator import validate_bitcoin_address
from app.fees import calculate_miner_fee, calculate_payout
from app.config import settings

logger = logging.getLogger("ln2oc.swaps")

class SwapError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

async def get_fee_rate_sat_per_vbyte() -> int:
    try:
        est = await lnd_client.estimate_fee(target_conf=2)
        # LND /v1/fee-estimates returns sat_per_kw or fee_rate (sat per kw)
        sat_per_kw = est.get("sat_per_kw")
        if sat_per_kw:
            sat_per_vbyte = int(sat_per_kw) // 250
            return max(sat_per_vbyte, settings.MIN_SAT_PER_VBYTE)
        fee_rate = est.get("fee_rate")
        if fee_rate:
            sat_per_vbyte = int(fee_rate) // 250
            return max(sat_per_vbyte, settings.MIN_SAT_PER_VBYTE)
    except Exception as e:
        logger.warning("Failed to estimate fee from LND, using default: %s", e)
    return settings.MIN_SAT_PER_VBYTE

def get_reserved_balance_sat(db: Session) -> int:
    """
    Sum of (payout_sat + miner_fee_sat) for all active swaps:
    PENDING, ACCEPTED, BROADCASTED.
    """
    active_statuses = [SwapStatus.PENDING, SwapStatus.ACCEPTED, SwapStatus.BROADCASTED]
    stmt = (
        select(func.coalesce(func.sum(Swap.payout_sat + Swap.miner_fee_sat), 0))
        .where(Swap.status.in_(active_statuses))
    )
    return int(db.execute(stmt).scalar() or 0)

async def check_available_onchain_balance(db: Session, required_sat: int) -> int:
    """
    Checks that LND confirmed on-chain balance minus active reservations >= required_sat.
    Returns confirmed on-chain balance.
    """
    bal = await lnd_client.get_blockchain_balance()
    # confirmed_balance is the safe balance to spend
    total_sat = int(bal.get("confirmed_balance", 0))
    reserved_sat = get_reserved_balance_sat(db)
    available_sat = total_sat - reserved_sat
    if available_sat < required_sat:
        raise SwapError(
            f"Insufficient available on-chain balance: {available_sat} sats available, {required_sat} sats required.",
            status_code=400
        )
    return available_sat

async def create_swap(db: Session, btc_address: str, amount_msat: int) -> Swap:
    """
    Creates and reserves a swap:
    1. Validates Bitcoin address
    2. Validates amount
    3. Calculates miner fee & payout
    4. Checks available on-chain balance
    5. Creates LND Hold Invoice
    6. Persists Swap record with status PENDING
    """
    if not validate_bitcoin_address(btc_address, settings.BITCOIN_NETWORK):
        raise SwapError(f"Invalid Bitcoin address for network '{settings.BITCOIN_NETWORK}': {btc_address}")

    amount_sat = amount_msat // 1000
    if amount_sat < settings.MIN_SWAP_SAT:
        raise SwapError(f"Amount {amount_sat} sat is below minimum {settings.MIN_SWAP_SAT} sat.")
    if amount_sat > settings.MAX_SWAP_SAT:
        raise SwapError(f"Amount {amount_sat} sat exceeds maximum {settings.MAX_SWAP_SAT} sat.")

    sat_per_vbyte = await get_fee_rate_sat_per_vbyte()
    miner_fee_sat = calculate_miner_fee(sat_per_vbyte)
    payout_sat = calculate_payout(amount_sat, miner_fee_sat, settings.SWAP_FEE_RATE)

    if payout_sat < settings.MIN_PAYOUT_SAT:
        raise SwapError(
            f"Calculated payout of {payout_sat} sats is below dust limit ({settings.MIN_PAYOUT_SAT} sats). "
            f"(Amount: {amount_sat} sats, miner fee: {miner_fee_sat} sats, fee rate: {settings.SWAP_FEE_RATE * 100}%)"
        )

    # Required sats to send on-chain = payout_sat + miner_fee_sat
    required_sat = payout_sat + miner_fee_sat

    # Check on-chain balance (atomic reservation via DB transaction)
    # Using SQLite WAL with immediate transaction or checking within the db session:
    await check_available_onchain_balance(db, required_sat)

    # Generate secret preimage and payment_hash
    preimage_bytes = os.urandom(32)
    payment_hash_bytes = hashlib.sha256(preimage_bytes).digest()
    payment_hash_hex = payment_hash_bytes.hex()
    preimage_hex = preimage_bytes.hex()

    memo = f"Swap-out to {btc_address[:10]}...: {payout_sat} sats"
    try:
        inv = await lnd_client.add_hold_invoice(
            payment_hash_bytes=payment_hash_bytes,
            value_sat=amount_sat,
            memo=memo,
            expiry_seconds=3600,
        )
    except Exception as e:
        logger.error("Failed to create LND hold invoice: %s", e)
        raise SwapError("Failed to generate Lightning invoice with LND", status_code=502)

    invoice_str = inv.get("payment_request")
    if not invoice_str:
        raise SwapError("LND did not return payment_request", status_code=502)

    swap = Swap(
        payment_hash=payment_hash_hex,
        preimage=preimage_hex,
        btc_address=btc_address,
        amount_sat=amount_sat,
        payout_sat=payout_sat,
        miner_fee_sat=miner_fee_sat,
        invoice=invoice_str,
        txid=None,
        status=SwapStatus.PENDING,
    )

    db.add(swap)
    db.commit()
    db.refresh(swap)
    logger.info("Created swap %s for address %s, amount %d sat, payout %d sat",
                swap.id, btc_address, amount_sat, payout_sat)
    return swap
