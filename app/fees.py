import math
from app.config import settings

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


def calculate_gross(amount_sat: int, fee_rate: float | None = None) -> int:
    """What the user gets before mining: floor(amount_sat * (1 - fee_rate)), exact integer
    math (fee_rate in basis points). The operator keeps exactly amount_sat - gross.
    The miner fee is not known here: it is set when the payout is signed, from the real
    tx at the rate of that moment, and the user receives gross - miner fee."""
    if fee_rate is None:
        fee_rate = settings.SWAP_FEE_RATE
    keep_bps = 10_000 - int(round(fee_rate * 10_000))
    return (amount_sat * keep_bps) // 10_000


def split_service_fee(amount_sat: int, gross_sat: int, with_community: bool) -> tuple[int, int]:
    """(operator_fee_sat, community_fee_sat) of the service fee amount_sat - gross_sat.
    The community gets floor(amount_sat * COMMUNITY_FEE_RATE), the operator the rest:
    rounding always goes to the house."""
    fee = amount_sat - gross_sat
    community = 0
    if with_community:
        community = (amount_sat * int(round(settings.COMMUNITY_FEE_RATE * 10_000))) // 10_000
    operator = fee - community
    assert 0 <= community <= fee and operator + community + gross_sat == amount_sat
    return operator, community
