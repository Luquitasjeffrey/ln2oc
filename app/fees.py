import math
from app.config import settings

# Payout tx budget charged to the user: ~1-2 inputs + recipient + change.
# If LND's actual coin selection costs more than what we charged, the swap is
# canceled (refunded) instead of the operator absorbing the difference.
ESTIMATED_TX_VBYTES = 160


class FeeEstimateError(Exception):
    pass


def sat_per_kw_to_sat_per_vbyte(sat_per_kw: int) -> int:
    # 1 vbyte = 4 weight units -> sat/vB = sat/kw * 4 / 1000. Round up: never underpay.
    return math.ceil(sat_per_kw / 250)


def current_fee_rate_sat_per_vbyte(lnd) -> int:
    """Fee rate from LND. Raises (never falls back silently) on missing/absurd data.
    LndUnavailable propagates so callers can distinguish a transient failure."""
    sat_per_kw = lnd.estimate_fee_sat_per_kw(settings.FEE_TARGET_CONF)
    if sat_per_kw <= 0:
        raise FeeEstimateError(f"LND returned non-positive fee estimate: {sat_per_kw} sat/kw")
    rate = max(sat_per_kw_to_sat_per_vbyte(sat_per_kw), settings.MIN_SAT_PER_VBYTE)
    if rate > settings.MAX_SAT_PER_VBYTE:
        raise FeeEstimateError(
            f"Fee estimate {rate} sat/vB exceeds MAX_SAT_PER_VBYTE={settings.MAX_SAT_PER_VBYTE}"
        )
    return rate


def calculate_miner_fee(sat_per_vbyte: int) -> int:
    return ESTIMATED_TX_VBYTES * sat_per_vbyte


def calculate_payout(amount_sat: int, miner_fee_sat: int, fee_rate: float | None = None) -> int:
    """payout = floor(amount_sat * (1 - fee_rate)) - miner_fee_sat, in exact integer math
    (fee_rate expressed in basis points)."""
    if fee_rate is None:
        fee_rate = settings.SWAP_FEE_RATE
    keep_bps = 10_000 - int(round(fee_rate * 10_000))
    return (amount_sat * keep_bps) // 10_000 - miner_fee_sat
