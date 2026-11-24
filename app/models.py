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

        PENDING ─(paid: invoice ACCEPTED)─► INVOICE_HOLD ─(settle + payout tx sent, same tick)─► SUCCESS
           │                                    │
           ▼                                    ▼
        EXPIRED (never paid)                 FAILED (refunded: hold invoice canceled)

        MANUAL_REVIEW: anything outside the rules (an invariant broke, or an edge case
                       nobody handles yet). The service halts and refuses to start
                       until an operator resolves it.
    """
    PENDING = "PENDING"                # hold invoice issued, waiting for payment
    INVOICE_HOLD = "INVOICE_HOLD"      # paid, hold invoice ACCEPTED: waits for the next payout
    SUCCESS = "SUCCESS"                # invoice settled and payout tx sent (terminal)
    FAILED = "FAILED"                  # refunded: hold invoice canceled, payer keeps their sats (terminal)
    EXPIRED = "EXPIRED"                # invoice expired/canceled unpaid (terminal)
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
    payout_sat = Column(BigInteger, nullable=True)  # set on SUCCESS: gross_sat - actual_fee_sat
    fee_rate_sat_vb = Column(Integer, nullable=True)  # rate the payout tx was funded at
    invoice = Column(Text, nullable=False)

    # Payout transaction (set on SUCCESS). Shared by every swap paid in the same tick:
    # one tx pays all of them, one output each.
    raw_tx = Column(Text, nullable=True)  # hex
    txid = Column(String(64), nullable=True, index=True)
    actual_fee_sat = Column(BigInteger, nullable=True)  # this swap's share of the miner fee

    status = Column(Enum(SwapStatus), default=SwapStatus.PENDING, nullable=False, index=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    __table_args__ = (
        Index("ix_swaps_status_created_at", "status", "created_at"),
    )
