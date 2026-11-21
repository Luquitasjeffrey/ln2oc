import hashlib
import logging
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.fees import calculate_gross
from app.halt import is_halted
from app.lnd import LndError, LndUnavailable, lnd_client
from app.models import Swap, SwapStatus
from app.validator import validate_bitcoin_address

logger = logging.getLogger("ln2oc.swaps")

class SwapError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_spendable_onchain_balance_sat() -> int:
    """What the wallet could spend right now. LND already excludes UTXOs leased by an
    in-flight payout from confirmed_balance, and keeps the anchor reserve unspendable.

    NOTHING is reserved for unpaid invoices: liquidity is only committed when a payment
    is actually held (the worker checks the balance then, or cancels the hold invoice
    if there are no funds at that moment). Otherwise anyone could lock our liquidity
    for free by requesting invoices and never paying them."""
    bal = lnd_client.wallet_balance()
    return int(bal.confirmed_balance) - int(bal.reserved_balance_anchor_chan)


def create_swap(db: Session, btc_address: str, amount_msat: int) -> Swap:
    """
    Validates the request and issues a hold invoice. Reserves nothing: the funds
    check that matters happens when the payment is held (the worker checks the
    on-chain balance before settling); if funds are missing then, the hold invoice is
    canceled and the payer keeps their sats.
    """
    if is_halted():
        raise SwapError("Service halted", status_code=503)

    # Every PENDING invoice is looked up on each poll: cap them so an attacker requesting
    # invoices for free cannot grow that work without bound.
    pending = db.execute(select(func.count()).select_from(Swap).where(Swap.status == SwapStatus.PENDING)).scalar_one()
    if pending >= settings.MAX_PENDING_SWAPS:
        logger.warning("Refusing new swap: %d PENDING swaps (MAX_PENDING_SWAPS=%d)", pending, settings.MAX_PENDING_SWAPS)
        raise SwapError("Too many pending swaps, try again later", status_code=503)

    if not validate_bitcoin_address(btc_address, settings.BITCOIN_NETWORK):
        raise SwapError(f"Invalid Bitcoin address for network '{settings.BITCOIN_NETWORK}': {btc_address}")

    if amount_msat % 1000 != 0:
        raise SwapError("Amount must be a whole number of satoshis.")
    amount_sat = amount_msat // 1000
    if amount_sat < settings.MIN_SWAP_SAT:
        raise SwapError(f"Amount {amount_sat} sat is below minimum {settings.MIN_SWAP_SAT} sat.")
    if amount_sat > settings.MAX_SWAP_SAT:
        raise SwapError(f"Amount {amount_sat} sat exceeds maximum {settings.MAX_SWAP_SAT} sat.")

    # No miner fee here: it is set when the payout is signed (real tx, rate of that moment).
    gross_sat = calculate_gross(amount_sat, settings.SWAP_FEE_RATE)
    if gross_sat < settings.MIN_PAYOUT_SAT:
        raise SwapError(f"Amount {amount_sat} sat leaves {gross_sat} sat after the service fee, below dust "
                        f"({settings.MIN_PAYOUT_SAT} sat).")
    required_sat = gross_sat

    preimage_bytes = os.urandom(32)
    payment_hash_bytes = hashlib.sha256(preimage_bytes).digest()
    lock_id = os.urandom(32)

    # Fail fast if we obviously could not pay this right now. Not a reservation.
    try:
        spendable = get_spendable_onchain_balance_sat()
    except (LndUnavailable, LndError) as e:
        logger.error("Could not read on-chain balance: %s", e)
        raise SwapError("Lightning node unavailable, try again later.", status_code=503)
    if spendable < required_sat:
        raise SwapError(
            f"Insufficient available on-chain balance: {spendable} sats available, {required_sat} sats required.",
            status_code=400,
        )

    memo = f"Swap-out to {btc_address[:10]}...: {gross_sat} sats minus the on-chain miner fee at payout"
    try:
        inv = lnd_client.add_hold_invoice(
            payment_hash=payment_hash_bytes,
            value_sat=amount_sat,
            memo=memo,
            expiry_seconds=settings.INVOICE_EXPIRY_SECONDS,
            cltv_expiry=settings.HOLD_INVOICE_CLTV_EXPIRY,
        )
    except (LndUnavailable, LndError) as e:
        # If the invoice was created but we never answered, nobody has the payment
        # request, so it cannot be paid; it simply expires.
        logger.error("Failed to create LND hold invoice: %s", e)
        raise SwapError("Failed to generate Lightning invoice with LND", status_code=502)

    invoice_str = inv.payment_request
    if not invoice_str:
        raise SwapError("LND did not return payment_request", status_code=502)

    swap = Swap(
        payment_hash=payment_hash_bytes.hex(),
        preimage=preimage_bytes.hex(),
        btc_address=btc_address,
        amount_sat=amount_sat,
        gross_sat=gross_sat,
        invoice=invoice_str,
        lock_id=lock_id.hex(),
        status=SwapStatus.PENDING,
    )
    db.add(swap)
    db.commit()
    db.refresh(swap)

    logger.info("Created swap %s for address %s, amount %d sat, %d sat minus miner fee",
                swap.id, btc_address, amount_sat, gross_sat)
    return swap
