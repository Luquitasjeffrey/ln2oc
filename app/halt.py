"""
Fail-loud machinery.

Philosophy: an outage is always preferable to losing funds. When an invariant that
protects money is violated, we stop *everything* (no new invoices, no payouts) and
require a human to look at it.
"""
import logging
import os

logger = logging.getLogger("ln2oc.halt")

_halted_reason: str | None = None


class FatalSwapError(Exception):
    """An invariant protecting funds was violated (or an edge case nobody handles yet
    happened) for some swaps.

    Those swaps are flagged MANUAL_REVIEW and the process halts. The service refuses to
    start again until an operator resolves every MANUAL_REVIEW swap.
    """

    def __init__(self, swap_ids: int | list[int] | None, message: str):
        self.swap_ids = [] if swap_ids is None else [swap_ids] if isinstance(swap_ids, int) else list(swap_ids)
        super().__init__(f"swaps {self.swap_ids}: {message}")
        self.message = message


def is_halted() -> bool:
    return _halted_reason is not None


def halted_reason() -> str | None:
    return _halted_reason


def halt_process(reason: str, exit_code: int = 70) -> None:
    """Stop accepting work immediately and terminate the process."""
    global _halted_reason
    _halted_reason = reason
    logger.critical("HALTING ln2oc: %s", reason)
    logging.shutdown()
    os._exit(exit_code)
