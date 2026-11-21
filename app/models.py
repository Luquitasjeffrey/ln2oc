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

        PENDING ──(invoice ACCEPTED)──► FUNDING ──(tx signed, persisted)──► SIGNED
           │                              │                                  │
           │                              └──────► CANCELING ◄───────────────┤
           │                                          │                      │ (invoice settled:
           ▼                                          ▼                      ▼  LN money is ours)
        EXPIRED (never paid)                       FAILED (refunded)        PAID
                                                                             │ (publish stored tx;
                                                                             ▼  idempotent retry)
                                                                         BROADCASTED

        MANUAL_REVIEW: an invariant protecting funds broke. Service halts and refuses
                       to start until an operator resolves it.
    """
    PENDING = "PENDING"          # hold invoice issued, waiting for payment
    FUNDING = "FUNDING"          # payment held; selecting/leasing UTXOs and signing
    SIGNED = "SIGNED"            # signed payout tx stored (NOT broadcast); invoice still held
    PAID = "PAID"                # invoice settled; must broadcast the stored tx
    BROADCASTED = "BROADCASTED"  # payout tx accepted by LND/mempool (terminal)
    CANCELING = "CANCELING"      # decided to refund: release leases + cancel hold invoice
    FAILED = "FAILED"            # hold invoice canceled, nothing paid on-chain (terminal)
    EXPIRED = "EXPIRED"          # invoice expired/canceled unpaid (terminal)
    MANUAL_REVIEW = "MANUAL_REVIEW"


ACTIVE_RESERVATION_STATUSES = (
    SwapStatus.PENDING,
    SwapStatus.FUNDING,
    SwapStatus.SIGNED,
    SwapStatus.PAID,
    SwapStatus.CANCELING,
    SwapStatus.MANUAL_REVIEW,
)

IN_FLIGHT_STATUSES = (
    SwapStatus.FUNDING,
    SwapStatus.SIGNED,
    SwapStatus.PAID,
    SwapStatus.CANCELING,
)


def _now():
    return datetime.now(timezone.utc)


class Swap(Base):
    __tablename__ = "swaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_hash = Column(String(64), unique=True, nullable=False, index=True)
    preimage = Column(String(64), nullable=False)  # Secret to settle hold invoice
    btc_address = Column(String(128), nullable=False)
    amount_sat = Column(BigInteger, nullable=False)
    payout_sat = Column(BigInteger, nullable=False)
    miner_fee_sat = Column(BigInteger, nullable=False)  # max on-chain fee charged to the user
    invoice = Column(Text, nullable=False)
    lock_id = Column(String(64), nullable=False)  # hex, LND UTXO lease id for this swap

    # Payout transaction (set in FUNDING -> SIGNED, never changed afterwards)
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
