import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    Enum,
    Index,
)
from app.db import Base


class SwapStatus(str, enum.Enum):
    """
    Swap lifecycle. The worker is the only writer after PENDING; every transition is
    a compare-and-set on the current status (see worker._transition).

        PENDING ──(invoice ACCEPTED)──► SETTLING ──(invoice SETTLED)──► PAID ──(tx signed, stored)──► SIGNED ──► BROADCASTED
           │                              │  only checks on-chain balance     │                          (publish stored tx,
           │                              │  + CLTV margin, then settles      │ funds + signs only now      idempotent retry)
           ▼                              ▼
        EXPIRED (never paid)           CANCELING ──► FAILED (hold invoice canceled: payer keeps their sats)

        From PAID on, the operator holds the payer's money: failures there are never
        refunded automatically, they go to MANUAL_REVIEW.

        MANUAL_REVIEW: an invariant protecting funds broke. Service halts and refuses
                       to start until an operator resolves it.
    """
    PENDING = "PENDING"          # hold invoice issued, waiting for payment
    SETTLING = "SETTLING"        # payment held; balance checked, settling the invoice
    PAID = "PAID"                # invoice SETTLED (LN money is ours); must fund + sign the payout
    SIGNED = "SIGNED"            # signed payout tx stored (NOT broadcast yet)
    BROADCASTED = "BROADCASTED"  # payout tx accepted by LND/mempool (terminal)
    CANCELING = "CANCELING"      # decided to refund: cancel hold invoice (+ release leases)
    FAILED = "FAILED"            # hold invoice canceled, nothing paid on-chain (terminal)
    EXPIRED = "EXPIRED"          # invoice expired/canceled unpaid (terminal)
    MANUAL_REVIEW = "MANUAL_REVIEW"


def _now():
    return datetime.now(timezone.utc)


class Swap(Base):
    __tablename__ = "swaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_hash = Column(String(64), unique=True, nullable=False, index=True)
    preimage = Column(String(64), nullable=False)  # Secret to settle hold invoice
    btc_address = Column(String(128), nullable=False)
    amount_sat = Column(BigInteger, nullable=False)
    gross_sat = Column(BigInteger, nullable=False)  # amount - service fee: payout + miner fee come out of it
    max_miner_fee_sat = Column(BigInteger, nullable=True)  # set before settling: cap on the payout's miner fee
    payout_sat = Column(BigInteger, nullable=True)  # set when signing: gross_sat - actual_fee_sat
    fee_rate_sat_vb = Column(Integer, nullable=True)  # rate estimated when signing the payout
    invoice = Column(Text, nullable=False)
    lock_id = Column(String(64), nullable=False)  # hex, LND UTXO lease id for this swap

    # Payout transaction (set in PAID -> SIGNED, never changed afterwards)
    raw_tx = Column(Text, nullable=True)  # hex
    txid = Column(String(64), nullable=True, unique=True)
    actual_fee_sat = Column(BigInteger, nullable=True)

    status = Column(Enum(SwapStatus), default=SwapStatus.PENDING, nullable=False, index=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    __table_args__ = (
        Index("ix_swaps_status_created_at", "status", "created_at"),
    )
