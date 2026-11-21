import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    DateTime,
    Enum,
    Index,
)
from app.db import Base

class SwapStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    BROADCASTED = "BROADCASTED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class Swap(Base):
    __tablename__ = "swaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_hash = Column(String(64), unique=True, nullable=False, index=True)
    preimage = Column(String(64), nullable=True)  # Secret to settle hold invoice
    btc_address = Column(String(128), nullable=False)
    amount_sat = Column(BigInteger, nullable=False)
    payout_sat = Column(BigInteger, nullable=False)
    miner_fee_sat = Column(BigInteger, nullable=False)
    invoice = Column(String, nullable=False)
    txid = Column(String(64), nullable=True)
    status = Column(Enum(SwapStatus), default=SwapStatus.PENDING, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_swaps_status_created_at", "status", "created_at"),
    )
