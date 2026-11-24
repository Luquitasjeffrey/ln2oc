"""
Paying several held payments in one tx: they wait while the wallet has an unconfirmed
tx, then one tx pays all of them (one output each, the miner fee split equally). What
the rules reject is refunded: a repeated destination, and from the first payment that
does not fit the balance, it and every later one.
"""
import time

from app.config import settings
from app.lnd import InvoiceState, lnd_client
from app.models import Swap, SwapStatus
from app.tx import parse_tx
from app.worker import SwapWorker
from tests.conftest import (
    get_swap, insert_swap, mine_blocks, new_dest_address, received_by, send_to_kross_unconfirmed,
)

_DONE = {SwapStatus.SUCCESS, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW}


def _held_while_wallet_busy(env, payer, grosses, addresses=None):
    """Pays one swap per gross while an incoming deposit is unconfirmed: every payment
    is held and nothing else happens. Then mines, so the next tick pays them.
    Returns [(swap_id, dest, payment future)] in creation order."""
    send_to_kross_unconfirmed(0.001)
    swaps = []
    for i, gross in enumerate(grosses):
        dest = addresses[i] if addresses else new_dest_address()
        swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=gross, address=dest)
        swaps.append((swap_id, dest, payer.pay(invoice)))
    for swap_id, _, _ in swaps:
        payment_hash = bytes.fromhex(get_swap(env["Session"], swap_id).payment_hash)
        deadline = time.monotonic() + 30
        while lnd_client.lookup_invoice(payment_hash).state != InvoiceState.ACCEPTED:
            assert time.monotonic() < deadline, f"swap {swap_id} never ACCEPTED"
            time.sleep(0.1)
    assert env["worker"].run_tick_guarded() is True  # held, waiting for the deposit to confirm
    assert all(get_swap(env["Session"], s[0]).status == SwapStatus.INVOICE_HOLD for s in swaps)
    mine_blocks(1)
    return swaps


def _tick_all(env, swap_ids, max_ticks: int = 60) -> list[Swap]:
    for _ in range(max_ticks):
        env["worker"].run_tick_guarded()
        swaps = [get_swap(env["Session"], i) for i in swap_ids]
        if all(s.status in _DONE for s in swaps) or env["fatal"].reasons:
            return swaps
        time.sleep(0.25)
    return [get_swap(env["Session"], i) for i in swap_ids]


def _assert_one_tx_pays(swaps: list[Swap], dests: list[str]) -> None:
    assert all(s.status == SwapStatus.SUCCESS for s in swaps), [(s.id, s.status, s.error) for s in swaps]
    assert len({s.txid for s in swaps}) == 1
    tx = parse_tx(bytes.fromhex(swaps[0].raw_tx))
    assert len(tx.outputs) == len(swaps) + 1  # one per swap + our change
    assert len({s.actual_fee_sat for s in swaps}) == 1  # equal shares
    for s, dest in zip(swaps, dests):
        assert received_by(dest) == s.payout_sat == s.gross_sat - s.actual_fee_sat
        assert lnd_client.lookup_invoice(bytes.fromhex(s.payment_hash)).state == InvoiceState.SETTLED


def test_held_payments_are_paid_together_in_one_tx(env, payer):
    swaps = _held_while_wallet_busy(env, payer, [40_000, 30_000, 20_000])
    done = _tick_all(env, [s[0] for s in swaps])
    assert not env["fatal"].reasons, env["fatal"].reasons
    _assert_one_tx_pays(done, [s[1] for s in swaps])
    for _, _, payment in swaps:
        assert payment.result(timeout=60).payment_error == ""
    mine_blocks(1)


def test_from_the_first_that_does_not_fit_every_later_one_is_refunded(env, payer, monkeypatch):
    """Balance 90k: 40k + 40k fit; 20k would not, so it and the 10k after it (which
    alone would fit) are refunded: they came later."""
    swaps = _held_while_wallet_busy(env, payer, [40_000, 40_000, 20_000, 10_000])
    monkeypatch.setattr(SwapWorker, "_spendable_sat", lambda self: 90_000)
    done = _tick_all(env, [s[0] for s in swaps])
    assert not env["fatal"].reasons, env["fatal"].reasons
    _assert_one_tx_pays(done[:2], [s[1] for s in swaps[:2]])
    for s, (_, _, payment) in zip(done[2:], swaps[2:]):
        assert s.status == SwapStatus.FAILED and "insufficient" in s.error, s.error
        assert payment.result(timeout=60).payment_error != ""
    mine_blocks(1)


def test_repeated_destination_is_refunded_the_rest_paid(env, payer):
    dest = new_dest_address()
    other = new_dest_address()
    swaps = _held_while_wallet_busy(env, payer, [40_000, 40_000, 30_000], addresses=[dest, dest, other])
    done = _tick_all(env, [s[0] for s in swaps])
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert done[1].status == SwapStatus.FAILED and "same address" in done[1].error, done[1].error
    assert swaps[1][2].result(timeout=60).payment_error != ""
    _assert_one_tx_pays([done[0], done[2]], [dest, other])
    mine_blocks(1)


def test_miner_fee_rate_above_the_max_refunds_everyone(env, payer, monkeypatch):
    from app.config import settings
    swaps = _held_while_wallet_busy(env, payer, [40_000, 40_000])
    monkeypatch.setattr(settings, "MAX_SAT_PER_VBYTE", 1)
    done = _tick_all(env, [s[0] for s in swaps])
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert all(s.status == SwapStatus.FAILED and "MAX_SAT_PER_VBYTE" in s.error for s in done)


def test_the_onchain_reserve_is_never_paid_out(env, payer, monkeypatch):
    """A payout that would leave less than ONCHAIN_RESERVE_SAT in the wallet is refunded:
    otherwise its change could be dust, LND would add it to the miner fee and the tx
    would pay more than the users were charged, after the settle."""
    swaps = _held_while_wallet_busy(env, payer, [45_000])
    monkeypatch.setattr(SwapWorker, "_spendable_sat", lambda self: 45_000 + settings.ONCHAIN_RESERVE_SAT - 1)
    done = _tick_all(env, [s[0] for s in swaps])
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert done[0].status == SwapStatus.FAILED and "reserve" in done[0].error, done[0].error
    assert swaps[0][2].result(timeout=60).payment_error != ""
    mine_blocks(1)
