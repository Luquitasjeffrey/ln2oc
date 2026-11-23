"""
Batched payouts: payments held while the wallet had unconfirmed txs are paid together,
in one tx with one output each, once every wallet tx confirms. Edge cases: what does not
fit is refunded and the rest is paid, a crash between two settles, a member lost after
another was settled, a failure after settling halts the whole batch.
"""
import time

import grpc
import pytest

from app.config import settings
from app.lnd import InvoiceState, LndError, LndUnavailable, lnd_client
from app.models import Swap, SwapStatus
from app.tx import parse_tx
from app.worker import SwapWorker, split_miner_fee
from tests.conftest import (
    get_swap, insert_swap, leases_for, mine_blocks, new_dest_address, received_by, send_to_kross_unconfirmed,
)

_DONE = {SwapStatus.BROADCASTED, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW}


def _wait_accepted(Session, swap_id: int, timeout: float = 30.0) -> None:
    payment_hash = bytes.fromhex(get_swap(Session, swap_id).payment_hash)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if lnd_client.lookup_invoice(payment_hash).state == InvoiceState.ACCEPTED:
            return
        time.sleep(0.1)
    raise AssertionError(f"invoice of swap {swap_id} never reached ACCEPTED")


def _held_while_wallet_busy(env, payer, grosses, addresses=None):
    """Pays one swap per gross while an incoming deposit is unconfirmed: the worker sees
    every payment held and takes none. Then mines, so the next tick starts the batch.
    Returns [(swap_id, dest, payment future)] in creation order."""
    send_to_kross_unconfirmed(0.001)
    swaps = []
    for i, gross in enumerate(grosses):
        dest = addresses[i] if addresses else new_dest_address()
        swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=gross, address=dest)
        swaps.append((swap_id, dest, payer.pay(invoice)))
    for swap_id, _, _ in swaps:
        _wait_accepted(env["Session"], swap_id)
    assert env["worker"].run_tick_guarded() is True  # held, waiting for the deposit to confirm
    for swap_id, _, _ in swaps:
        swap = get_swap(env["Session"], swap_id)
        assert swap.status == SwapStatus.PENDING and swap.batch_id is None, swap.status
    mine_blocks(1)
    return swaps


def _tick_all(env, swap_ids, statuses=_DONE, max_ticks: int = 60) -> list[Swap]:
    for _ in range(max_ticks):
        env["worker"].run_tick_guarded()
        swaps = [get_swap(env["Session"], i) for i in swap_ids]
        if all(s.status in statuses for s in swaps) or env["fatal"].reasons:
            return swaps
        time.sleep(0.25)
    return [get_swap(env["Session"], i) for i in swap_ids]


def _assert_one_tx_pays(swaps: list[Swap], dests: list[str]) -> None:
    """All BROADCASTED by the same stored tx: one output per swap with its payout, at
    most one more (our change); payout + fee share == gross for each."""
    assert all(s.status == SwapStatus.BROADCASTED for s in swaps), [(s.id, s.status, s.error) for s in swaps]
    assert len({s.txid for s in swaps}) == 1 and len({s.raw_tx for s in swaps}) == 1
    assert len({s.batch_id for s in swaps}) == 1 and swaps[0].batch_id
    tx = parse_tx(bytes.fromhex(swaps[0].raw_tx))
    assert tx.txid == swaps[0].txid
    assert len(tx.outputs) in (len(swaps), len(swaps) + 1)
    for s, dest in zip(swaps, dests):
        assert received_by(dest) == s.payout_sat  # paid once, nothing else
        assert s.payout_sat + s.actual_fee_sat == s.gross_sat
        assert 0 < s.actual_fee_sat <= s.max_miner_fee_sat
        assert lnd_client.lookup_invoice(bytes.fromhex(s.payment_hash)).state == InvoiceState.SETTLED
    inputs = {(i.txid, i.vout) for i in tx.inputs}
    leased = {(l.outpoint.txid_str, l.outpoint.output_index) for l in leases_for(swaps[0].batch_id)}
    assert leased <= inputs


# --------------------------------------------------------------------- unit


def test_split_miner_fee_is_proportional_to_caps_and_never_above_them():
    assert split_miner_fee(3000, [10_000, 10_000, 10_000]) == [1000, 1000, 1000]
    assert split_miner_fee(3002, [10_000] * 3) == [1001, 1001, 1000]  # leftover to the oldest on ties
    # A payout that needs many inputs (big cap) pays for them; the small one does not.
    assert split_miner_fee(800, [1480, 220]) == [696, 104]
    assert split_miner_fee(777, [5000]) == [777]  # a batch of one pays exactly as before
    assert split_miner_fee(5000, [1000, 2000]) == [1000, 2000]  # caps do not cover it: tx pays less
    import random
    rnd = random.Random(7)
    for _ in range(2000):
        caps = [rnd.randint(1, 50_000) for _ in range(rnd.randint(1, 12))]
        total = rnd.randint(1, sum(caps) * 2)
        shares = split_miner_fee(total, caps)
        assert all(0 <= s <= c for s, c in zip(shares, caps))
        assert sum(shares) == min(total, sum(caps))
    for bad in ((0, [1]), (10, []), (10, [5, 0])):
        with pytest.raises(ValueError):
            split_miner_fee(*bad)


# --------------------------------------------------------------------- happy path


def test_held_payments_are_paid_together_in_one_tx(env, payer):
    swaps = _held_while_wallet_busy(env, payer, [40_000, 30_000, 20_000])
    ids, dests = [s[0] for s in swaps], [s[1] for s in swaps]
    done = _tick_all(env, ids)
    assert not env["fatal"].reasons, env["fatal"].reasons
    for _, _, payment in swaps:
        assert payment.result(timeout=60).payment_error == ""
    _assert_one_tx_pays(done, dests)

    tx = parse_tx(bytes.fromhex(done[0].raw_tx))
    tx_fee = sum(s.actual_fee_sat for s in done)
    # Shares in proportion to each one's cap (= what paying them alone would cost).
    cap_sum = sum(s.max_miner_fee_sat for s in done)
    for s in done:
        assert abs(s.actual_fee_sat - tx_fee * s.max_miner_fee_sat / cap_sum) <= 1
    assert abs(tx_fee - tx.vsize * done[0].fee_rate_sat_vb) <= done[0].fee_rate_sat_vb
    # Cheaper than alone: each cap is 2x the fee of paying that swap alone.
    for s in done:
        assert s.actual_fee_sat < s.max_miner_fee_sat / 2
    mine_blocks(1)
    for s, dest in zip(done, dests):
        assert received_by(dest, minconf=1) == s.payout_sat


def test_batch_size_is_capped_and_a_repeated_destination_waits(env, payer, monkeypatch):
    """MAX_PAYOUT_BATCH=2 and swaps 0 and 1 pay the same address: the first batch takes
    0 and 2 (1 waits: one output per destination; 3 waits: batch full). Once that payout
    confirms, the next batch pays 1 and 3."""
    monkeypatch.setattr(settings, "MAX_PAYOUT_BATCH", 2)
    shared = new_dest_address()
    addresses = [shared, shared, new_dest_address(), new_dest_address()]
    swaps = _held_while_wallet_busy(env, payer, [40_000] * 4, addresses=addresses)
    ids = [s[0] for s in swaps]

    first = _tick_all(env, [ids[0], ids[2]])
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert first[0].txid == first[1].txid
    waiting = [get_swap(env["Session"], ids[i]) for i in (1, 3)]
    assert all(s.status == SwapStatus.PENDING and s.batch_id is None for s in waiting)
    # Waiting for our own payout to confirm: still held, nothing refunded.
    assert env["worker"].run_tick_guarded() is True
    assert all(get_swap(env["Session"], ids[i]).status == SwapStatus.PENDING for i in (1, 3))

    mine_blocks(1)
    second = _tick_all(env, [ids[1], ids[3]])
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert second[0].txid == second[1].txid != first[0].txid
    for _, _, payment in swaps:
        assert payment.result(timeout=60).payment_error == ""
    assert received_by(shared) == first[0].payout_sat + second[0].payout_sat
    assert received_by(addresses[2]) == first[1].payout_sat
    assert received_by(addresses[3]) == second[1].payout_sat
    mine_blocks(1)


# --------------------------------------------------------------------- refunds inside a batch


def test_what_does_not_fit_is_refunded_and_the_rest_is_paid(env, payer, monkeypatch):
    """Oldest first: the balance check adds up the whole batch (gross + cap of each).
    With room for two payouts, the third is refunded; a payout that would be dust at its
    cap is refunded too. The others are paid in one tx."""
    swaps = _held_while_wallet_busy(env, payer, [40_000, 2_000, 40_000, 40_000])
    ids, dests = [s[0] for s in swaps], [s[1] for s in swaps]
    monkeypatch.setattr(SwapWorker, "_spendable_sat", lambda self: 100_000)  # ~2 x (40k + cap)
    done = _tick_all(env, ids)
    assert not env["fatal"].reasons, env["fatal"].reasons

    dust, last = done[1], done[3]
    assert dust.status == SwapStatus.FAILED and "below dust" in dust.error, dust.error
    assert last.status == SwapStatus.FAILED and "after the rest of the batch" in last.error, last.error
    for refused, (_, _, payment) in ((dust, swaps[1]), (last, swaps[3])):
        assert payment.result(timeout=60).payment_error != ""  # payer got their money back
        assert lnd_client.lookup_invoice(bytes.fromhex(refused.payment_hash)).state == InvoiceState.CANCELED
        assert refused.raw_tx is None and received_by(dests[done.index(refused)]) == 0
    _assert_one_tx_pays([done[0], done[2]], [dests[0], dests[2]])
    for i in (0, 2):
        assert swaps[i][2].result(timeout=60).payment_error == ""
    mine_blocks(1)


def test_member_lost_after_another_was_settled_is_refunded_rest_paid(env, payer, monkeypatch):
    """The second HTLC is canceled right after the first invoice is settled (e.g. by LND
    near expiry): that payer is refunded, the first is paid alone."""
    swaps = _held_while_wallet_busy(env, payer, [40_000, 40_000])
    ids = [s[0] for s in swaps]
    second_hash = bytes.fromhex(get_swap(env["Session"], ids[1]).payment_hash)
    real_settle = lnd_client.settle_invoice
    calls = {"n": 0}

    def settle_then_lose_the_other(preimage):
        calls["n"] += 1
        real_settle(preimage)
        if calls["n"] == 1:
            lnd_client.cancel_invoice(second_hash)

    monkeypatch.setattr(lnd_client, "settle_invoice", settle_then_lose_the_other)
    done = _tick_all(env, ids)
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert done[1].status == SwapStatus.FAILED and "canceled" in done[1].error, done[1].error
    assert swaps[1][2].result(timeout=60).payment_error != ""
    _assert_one_tx_pays([done[0]], [swaps[0][1]])
    assert swaps[0][2].result(timeout=60).payment_error == ""
    assert len(parse_tx(bytes.fromhex(done[0].raw_tx)).outputs) == 2  # destination + change
    mine_blocks(1)


# --------------------------------------------------------------------- crashes and ambiguity


def test_crash_between_two_settles_resumes_without_rechecking(env, payer, monkeypatch):
    """The process dies after settling the first invoice of the batch and before the
    second. A fresh worker settles the second (no new balance check: the batch was
    checked as a whole before the first settle) and pays both in one tx."""
    swaps = _held_while_wallet_busy(env, payer, [40_000, 40_000])
    ids = [s[0] for s in swaps]
    real_settle = lnd_client.settle_invoice
    calls = {"n": 0}

    def die_before_second(preimage):
        calls["n"] += 1
        if calls["n"] == 2:
            raise LndUnavailable("injected: process died before settling")
        real_settle(preimage)

    monkeypatch.setattr(lnd_client, "settle_invoice", die_before_second)
    env["worker"].run_tick_guarded()
    states = [get_swap(env["Session"], i) for i in ids]
    assert [s.status for s in states] == [SwapStatus.SETTLING, SwapStatus.SETTLING]  # LND answer lost
    assert all(s.max_miner_fee_sat for s in states) and all(s.raw_tx is None for s in states)
    assert lnd_client.lookup_invoice(bytes.fromhex(states[0].payment_hash)).state == InvoiceState.SETTLED
    assert lnd_client.lookup_invoice(bytes.fromhex(states[1].payment_hash)).state == InvoiceState.ACCEPTED

    monkeypatch.undo()
    checks = []
    real_balance = lnd_client.wallet_balance
    monkeypatch.setattr(lnd_client, "wallet_balance", lambda: checks.append(1) or real_balance())
    fresh = SwapWorker(session_factory=env["Session"], lock_path=str(env["tmp_path"] / "w2.lock"),
                       on_fatal=env["fatal"])
    env["worker"] = fresh
    done = _tick_all(env, ids)
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert checks == []  # resumed: no new balance check after the first settle
    assert [d.max_miner_fee_sat for d in done] == [s.max_miner_fee_sat for s in states]
    _assert_one_tx_pays(done, [s[1] for s in swaps])
    for _, _, payment in swaps:
        assert payment.result(timeout=60).payment_error == ""
    mine_blocks(1)


def test_lost_publish_response_never_pays_a_batch_twice(env, payer, monkeypatch):
    swaps = _held_while_wallet_busy(env, payer, [40_000, 40_000])
    ids = [s[0] for s in swaps]
    real_publish = lnd_client.publish_transaction
    calls = {"n": 0}

    def lost_once(raw, label):
        calls["n"] += 1
        result = real_publish(raw, label)
        if calls["n"] == 1:
            raise LndUnavailable("injected: response lost after LND executed the call")
        return result

    monkeypatch.setattr(lnd_client, "publish_transaction", lost_once)
    done = _tick_all(env, ids)
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert calls["n"] == 2  # re-published the SAME stored tx
    _assert_one_tx_pays(done, [s[1] for s in swaps])
    mine_blocks(1)
    for s, (_, dest, _) in zip(done, swaps):
        assert received_by(dest, minconf=1) == s.payout_sat


@pytest.mark.parametrize("rate_after", [400])
def test_fee_spike_after_settle_is_capped_per_user(env, payer, monkeypatch, rate_after):
    """A spike between the settles and the signature: each user pays at most their cap,
    the tx pays (at most) the sum of the caps, no manual review."""
    import app.worker as worker_mod
    real_rate = worker_mod.current_fee_rate_sat_per_vbyte
    rate_calls = {"n": 0}

    def rate(lnd):
        rate_calls["n"] += 1
        return real_rate(lnd) if rate_calls["n"] == 1 else rate_after

    swaps = _held_while_wallet_busy(env, payer, [20_000, 20_000])
    monkeypatch.setattr(worker_mod, "current_fee_rate_sat_per_vbyte", rate)
    done = _tick_all(env, [s[0] for s in swaps])
    assert not env["fatal"].reasons, env["fatal"].reasons
    _assert_one_tx_pays(done, [s[1] for s in swaps])
    assert done[0].fee_rate_sat_vb < rate_after
    tx_fee = sum(s.actual_fee_sat for s in done)
    assert tx_fee <= sum(s.max_miner_fee_sat for s in done)
    assert tx_fee >= parse_tx(bytes.fromhex(done[0].raw_tx)).vsize * settings.MIN_SAT_PER_VBYTE
    assert all(s.actual_fee_sat <= s.max_miner_fee_sat for s in done)
    mine_blocks(1)


# --------------------------------------------------------------------- fail loud


def test_failure_after_settle_halts_the_whole_batch(env, payer, monkeypatch):
    def no_funds(**kw):
        raise LndError(grpc.StatusCode.UNKNOWN, "insufficient funds available to construct transaction", "FundPsbt")

    swaps = _held_while_wallet_busy(env, payer, [40_000, 40_000])
    monkeypatch.setattr(lnd_client, "fund_psbt", no_funds)
    done = _tick_all(env, [s[0] for s in swaps], statuses={SwapStatus.MANUAL_REVIEW})
    assert env["fatal"].reasons and "USER IS OWED" in env["fatal"].reasons[0]
    for s, (_, _, payment) in zip(done, swaps):
        assert s.status == SwapStatus.MANUAL_REVIEW and "USER IS OWED" in s.error, s.error
        assert s.raw_tx is None
        assert payment.result(timeout=60).payment_error == ""  # both payers were charged
        assert lnd_client.lookup_invoice(bytes.fromhex(s.payment_hash)).state == InvoiceState.SETTLED


def _force(Session, swap_id: int, **values) -> None:
    with Session() as db:
        db.query(Swap).filter(Swap.id == swap_id).update(values)
        db.commit()


def test_two_batches_in_flight_is_fatal(env):
    a, _ = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    b, _ = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    _force(env["Session"], a, status=SwapStatus.SETTLING, batch_id="aa" * 32)
    _force(env["Session"], b, status=SwapStatus.SETTLING, batch_id="bb" * 32)
    env["worker"].run_tick_guarded()
    assert env["fatal"].reasons and "not one batch" in env["fatal"].reasons[0]
    # Recorded in the DB, so the service refuses to start again until someone looks.
    assert get_swap(env["Session"], a).status == SwapStatus.MANUAL_REVIEW


def test_partly_signed_batch_is_fatal_and_flags_every_member(env):
    a, _ = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    b, _ = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    _force(env["Session"], a, status=SwapStatus.SIGNED, batch_id="cc" * 32)
    _force(env["Session"], b, status=SwapStatus.PAID, batch_id="cc" * 32)
    env["worker"].run_tick_guarded()
    assert env["fatal"].reasons and "partly signed" in env["fatal"].reasons[0]
    assert {get_swap(env["Session"], i).status for i in (a, b)} == {SwapStatus.MANUAL_REVIEW}


def test_address_that_no_longer_decodes_is_refunded_before_settle(env, payer):
    """A stored address that does not decode for this network (here: mainnet on regtest)
    is refunded before any settle; the rest of the batch is paid, nobody is halted."""
    mainnet = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
    ok_dest = new_dest_address()
    swaps = _held_while_wallet_busy(env, payer, [40_000, 40_000], addresses=[mainnet, ok_dest])
    done = _tick_all(env, [s[0] for s in swaps])
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert done[0].status == SwapStatus.FAILED and "no longer validates" in done[0].error, done[0].error
    assert swaps[0][2].result(timeout=60).payment_error != ""
    _assert_one_tx_pays([done[1]], [ok_dest])
    assert swaps[1][2].result(timeout=60).payment_error == ""
    mine_blocks(1)
