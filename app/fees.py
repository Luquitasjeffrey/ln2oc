import math
from app.config import settings

# Typical standard transaction: 1 P2WPKH input (~68 vbytes) + 2 outputs (P2WPKH recipient + P2WPKH change ~31+31 vbytes) + header (~10.5 vbytes) ~ 141 vbytes.
# With safety margin for 2 inputs or script addresses: ~150-180 vbytes.
ESTIMATED_TX_VBYTES = 160

def calculate_miner_fee(sat_per_vbyte: int) -> int:
    rate = max(sat_per_vbyte, settings.MIN_SAT_PER_VBYTE)
    return ESTIMATED_TX_VBYTES * rate

def calculate_payout(amount_sat: int, miner_fee_sat: int, fee_rate: float | None = None) -> int:
    """
    Spec: amount_sat * 994 // 1000 - miner_fee_sat
    With configurable fee rate: payout = int(amount_sat * (1 - fee_rate)) - miner_fee_sat
    When SWAP_FEE_RATE = 0.006: 1 - 0.006 = 0.994 -> amount_sat * 994 // 1000
    """
    if fee_rate is None:
        fee_rate = settings.SWAP_FEE_RATE

    # Exact integer math matching spec:
    # (1 - 0.006) = 994 / 1000
    # multiplier = round((1.0 - fee_rate) * 1000000)
    # payout_before_miner_fee = (amount_sat * multiplier) // 1000000
    multiplier = int(round((1.0 - fee_rate) * 1000))
    payout_before_miner_fee = (amount_sat * multiplier) // 1000
    return payout_before_miner_fee - miner_fee_sat
