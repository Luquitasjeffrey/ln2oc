"""
End-to-end tests against Polar regtest. Each money-loss scenario from the security
review is reproduced by injecting an *ambiguous* failure (the call succeeds in LND
but we never learn it) and checking that the payout happens exactly once.
"""
import hashlib
import os

import pytest

from app.config import settings
from app.fees import calculate_miner_fee, current_fee_rate_sat_per_vbyte
from app.lnd import InvoiceState, LndUnavailable, lnd_client
from app.models import SwapStatus
from app.swaps import SwapError, create_swap
from app.tx import parse_tx
from app.validator import address_to_script
from app.worker import SwapWorker
from tests.conftest import (
    get_bitcoind_tx, get_swap, insert_swap, leases_for, mine_blocks, new_dest_address,
    received_by, tick_until, wait_for_status,
)

REGTEST_ADDR = "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz"


def current_miner_fee() -> int:
    return calculate_miner_fee(current_fee_rate_sat_per_vbyte(lnd_client))


def ambiguous_once(real):
    """Wraps an LND call: performs it for real, then pretends the answer was lost."""
    state = {"calls": 0}

    def wrapper(*args, **kwargs):
        state["calls"] += 1
        result = real(*args, **kwargs)
        if state["calls"] == 1:
            raise LndUnavailable("injected: response lost after LND executed the call")
        return result

    wrapper.state = state
    return wrapper


def assert_paid_exactly_once(swap, dest: str):
    assert swap.status == SwapStatus.BROADCASTED, swap.error
    tx = get_bitcoind_tx(swap.txid)
    assert tx["txid"] == swap.txid == parse_tx(bytes.fromhex(swap.raw_tx)).txid
    assert received_by(dest) == swap.payout_sat  # nothing else ever paid to this address
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.SETTLED
    assert swap.actual_fee_sat <= swap.miner_fee_sat
    # Leases are kept on the (now spent) inputs until they expire; they must be exactly ours.
    inputs = {(i.txid, i.vout) for i in parse_tx(bytes.fromhex(swap.raw_tx)).inputs}
    leased = {(l.outpoint.txid_str, l.outpoint.output_index) for l in leases_for(swap.lock_id)}
    assert leased <= inputs


# --------------------------------------------------------------------- unit-ish


def test_address_to_script():
    assert address_to_script(REGTEST_ADDR, "regtest").hex().startswith("0014")
    assert address_to_script(REGTEST_ADDR, "mainnet") is None
    assert address_to_script(" " + REGTEST_ADDR, "regtest") is None
    assert address_to_script("bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr", "mainnet").hex() == \
        "0014de53ccc7ca843b51253dacdf7075b0c002ad9105"
    assert address_to_script("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "mainnet").hex() == \
        "76a91477bff20c60e522dfaa3350c39b030a5d004e839a88ac"
    assert address_to_script("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy", "mainnet").hex() == \
        "a914b472a266d0bd89c13706a4132ccfb16f7c3b9fcb87"


def test_process_lock_is_exclusive(env):
    path = str(env["tmp_path"] / "exclusive.lock")
    a = SwapWorker(session_factory=env["Session"], lock_path=path)
    b = SwapWorker(session_factory=env["Session"], lock_path=path)
    a.acquire_process_lock()
    try:
        with pytest.raises(RuntimeError, match="refusing to start a second"):
            b.acquire_process_lock()
    finally:
        a.release_process_lock()
    b.acquire_process_lock()
    b.release_process_lock()


# --------------------------------------------------------------------- LNURL


@pytest.mark.asyncio
async def test_lnurlp_validation_and_metadata(client):
    res = await client.get("/.well-known/lnurlp/invalid_address")
    assert res.status_code == 400
    res = await client.get(f"/.well-known/lnurlp/{REGTEST_ADDR}")
    assert res.status_code == 200
    data = res.json()
    assert data["tag"] == "payRequest"
    assert REGTEST_ADDR in data["callback"]


@pytest.mark.asyncio
async def test_lnurlp_rejects_bad_amounts(client):
    base = f"/lnurlp/cb?btc_address={REGTEST_ADDR}"
    res = await client.get(f"{base}&amount=500000")
    assert res.status_code == 400 and "below minimum" in res.json()["reason"]
    res = await client.get(f"{base}&amount=60000000000")
    assert res.status_code == 400 and "exceeds maximum" in res.json()["reason"]
    res = await client.get(f"{base}&amount=100000500")
    assert res.status_code == 400 and "whole number" in res.json()["reason"]


def test_insufficient_onchain_balance_rejected_upfront(env, monkeypatch):
    confirmed = int(lnd_client.wallet_balance().confirmed_balance)
    monkeypatch.setattr(settings, "MAX_SWAP_SAT", confirmed + 20_000_000)
    with env["Session"]() as db:
        with pytest.raises(SwapError, match="Insufficient available on-chain balance"):
            create_swap(db, REGTEST_ADDR, (confirmed + 10_000_000) * 1000)


def test_unpaid_invoices_do_not_lock_liquidity(env, monkeypatch):
    """Liquidity is committed only when a payment is held, never at invoice creation:
    unpaid invoices must not block each other (or anyone else)."""
    from app.swaps import get_spendable_onchain_balance_sat
    spendable = get_spendable_onchain_balance_sat()
    amount_sat = int(spendable * 0.8)
    monkeypatch.setattr(settings, "MAX_SWAP_SAT", amount_sat)
    monkeypatch.setattr(settings, "INVOICE_EXPIRY_SECONDS", 60)
    with env["Session"]() as db:
        for _ in range(3):  # 3 x 80% of the balance: would fail if PENDING reserved funds
            create_swap(db, REGTEST_ADDR, amount_sat * 1000)
    assert get_spendable_onchain_balance_sat() == spendable


# --------------------------------------------------------------------- happy path


@pytest.mark.asyncio
async def test_complete_e2e_swap(env, client, payer):
    dest = new_dest_address()
    res = await client.get(f"/lnurlp/cb?btc_address={dest}&amount={100_000 * 1000}")
    assert res.status_code == 200, res.text
    invoice = res.json()["pr"]

    with env["Session"]() as db:
        from app.models import Swap
        swap_id = db.query(Swap).filter_by(invoice=invoice).one().id

    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED})
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)
    assert received_by(dest, minconf=1) == swap.payout_sat


# --------------------------------------------------------------------- event-driven worker


def _event_driven_worker(env):
    """A real worker thread: it only learns about payments through SubscribeSingleInvoice."""
    w = SwapWorker(session_factory=env["Session"], retry_interval_seconds=0.2,
                   lock_path=str(env["tmp_path"] / "event.lock"), on_fatal=env["fatal"])
    env["worker"] = w
    return w


def test_subscription_picks_up_swaps_pending_at_startup(env, payer):
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=dest)
    worker = _event_driven_worker(env)
    worker.start()  # subscribes every PENDING swap before the worker loop starts
    assert worker.watcher.is_watching(swap_id)

    payment = payer.pay(invoice)
    swap = wait_for_status(env["Session"], swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW})
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    worker.stop()
    assert worker.watcher.watched_count() == 0
    mine_blocks(1)


def test_subscription_picks_up_new_swaps_and_expiry(env, payer):
    worker = _event_driven_worker(env)
    worker.start()

    # A new swap registered by the API path is processed as soon as it is paid.
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=dest)
    worker.notify_new_swap(swap_id, bytes.fromhex(get_swap(env["Session"], swap_id).payment_hash))
    payment = payer.pay(invoice)
    swap = wait_for_status(env["Session"], swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW})
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)

    # An invoice canceled/expired in LND is noticed through the stream too.
    other_id, _ = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                              miner_fee_sat=current_miner_fee(), address=new_dest_address())
    other = get_swap(env["Session"], other_id)
    worker.notify_new_swap(other_id, bytes.fromhex(other.payment_hash))
    lnd_client.cancel_invoice(bytes.fromhex(other.payment_hash))
    other = wait_for_status(env["Session"], other_id, {SwapStatus.EXPIRED})
    assert other.status == SwapStatus.EXPIRED
    assert not env["fatal"].reasons, env["fatal"].reasons
    worker.stop()
    mine_blocks(1)


def test_concurrent_payments_are_paid_one_after_another(env, payer):
    worker = _event_driven_worker(env)
    worker.start()
    swaps = []
    for _ in range(3):
        dest = new_dest_address()
        swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                       miner_fee_sat=current_miner_fee(), address=dest)
        worker.notify_new_swap(swap_id, bytes.fromhex(get_swap(env["Session"], swap_id).payment_hash))
        swaps.append((swap_id, dest, invoice))
    payments = [payer.pay(invoice) for _, _, invoice in swaps]  # all held at roughly the same time
    for (swap_id, dest, _), payment in zip(swaps, payments):
        swap = wait_for_status(env["Session"], swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW})
        assert payment.result(timeout=60).payment_error == "", swap.error
        assert_paid_exactly_once(swap, dest)
    assert not env["fatal"].reasons, env["fatal"].reasons
    worker.stop()
    mine_blocks(1)


def test_startup_refuses_more_pending_swaps_than_it_can_watch(env):
    for _ in range(2):
        insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                    miner_fee_sat=current_miner_fee(), address=new_dest_address())
    w = SwapWorker(session_factory=env["Session"], lock_path=str(env["tmp_path"] / "cap.lock"),
                   on_fatal=env["fatal"], max_watched_invoices=1)
    with pytest.raises(RuntimeError, match="MAX_WATCHED_INVOICES"):
        w.start()
    w.watcher.close()
    w.release_process_lock()


# --------------------------------------------------------------------- refunds


def test_no_onchain_funds_at_payment_time_refunds_payer(env, payer):
    """Criterion: cancel the hold invoice if on-chain balance is not available."""
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=10**15,
                                   miner_fee_sat=current_miner_fee(), address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.FAILED, SwapStatus.BROADCASTED})
    assert not env["fatal"].reasons
    assert swap.status == SwapStatus.FAILED and "cannot fund payout" in swap.error
    assert swap.raw_tx is None
    assert payment.result(timeout=60).payment_error != ""  # payer got their money back
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.CANCELED
    assert leases_for(swap.lock_id) == []


def test_fee_above_charged_refunds_payer(env, payer):
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=1, address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.FAILED, SwapStatus.BROADCASTED})
    assert swap.status == SwapStatus.FAILED and "exceeds charged" in swap.error
    assert payment.result(timeout=60).payment_error != ""
    assert leases_for(swap.lock_id) == []


def test_insufficient_cltv_margin_refunds_payer(env, payer, monkeypatch):
    monkeypatch.setattr(settings, "MIN_CLTV_MARGIN_BLOCKS", 10_000)
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.FAILED, SwapStatus.BROADCASTED})
    assert swap.status == SwapStatus.FAILED and "CLTV margin" in swap.error
    assert payment.result(timeout=60).payment_error != ""


# --------------------------------------------------------------------- ambiguous failures


def test_lost_fund_response_does_not_leak_or_double_fund(env, payer, monkeypatch):
    wrapped = ambiguous_once(lnd_client.fund_psbt)
    monkeypatch.setattr(lnd_client, "fund_psbt", wrapped)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=dest)
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED})
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert wrapped.state["calls"] == 2
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)


def test_lost_settle_response_is_recovered(env, payer, monkeypatch):
    wrapped = ambiguous_once(lnd_client.settle_invoice)
    monkeypatch.setattr(lnd_client, "settle_invoice", wrapped)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=dest)
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED})
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert wrapped.state["calls"] == 1  # second tick saw SETTLED and did not settle again
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)


def test_lost_publish_response_never_pays_twice(env, payer, monkeypatch):
    """The original bug: tx broadcast but response lost -> old code refunded AND paid."""
    wrapped = ambiguous_once(lnd_client.publish_transaction)
    monkeypatch.setattr(lnd_client, "publish_transaction", wrapped)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=dest)
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED})
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert wrapped.state["calls"] == 2  # re-published the SAME stored tx
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)
    assert received_by(dest, minconf=1) == swap.payout_sat


def test_restart_mid_payout_resumes_with_new_worker(env, payer, monkeypatch):
    """Simulate a crash right after the tx was signed and stored: a fresh worker
    (new process) must settle and publish that exact tx."""
    calls = {"n": 0}
    real_settle = lnd_client.settle_invoice

    def crash_before_settle(preimage):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LndUnavailable("injected: process died before settling")
        return real_settle(preimage)

    monkeypatch.setattr(lnd_client, "settle_invoice", crash_before_settle)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=dest)
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.SIGNED})
    assert swap.status == SwapStatus.SIGNED
    stored_txid = swap.txid

    fresh = SwapWorker(session_factory=env["Session"], lock_path=str(env["tmp_path"] / "w2.lock"),
                       on_fatal=env["fatal"])
    env["worker"] = fresh
    swap = tick_until(env, swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED})
    assert swap.txid == stored_txid
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)


# --------------------------------------------------------------------- fail loud


def test_invoice_settled_outside_flow_is_fatal(env, payer):
    preimage = os.urandom(32)
    payment_hash = hashlib.sha256(preimage).digest()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=new_dest_address())
    swap = get_swap(env["Session"], swap_id)
    payment = payer.pay(invoice)
    for _ in range(40):
        if lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.ACCEPTED:
            break
        import time; time.sleep(0.25)
    lnd_client.settle_invoice(bytes.fromhex(swap.preimage))  # someone settles behind our back
    payment.result(timeout=60)

    env["worker"].notify(swap_id)
    env["worker"].run_tick_guarded()
    assert env["fatal"].reasons and "SETTLED while swap PENDING" in env["fatal"].reasons[0]
    swap = get_swap(env["Session"], swap_id)
    assert swap.status == SwapStatus.MANUAL_REVIEW
    assert swap.raw_tx is None

    # While anything is in MANUAL_REVIEW the worker refuses to do anything else.
    env["worker"].run_tick_guarded()
    assert "MANUAL_REVIEW" in env["fatal"].reasons[-1]
    del preimage, payment_hash


def test_publish_rejected_after_settle_is_fatal(env, payer, monkeypatch):
    from app.lnd import LndError
    import grpc

    def reject(raw, label):
        raise LndError(grpc.StatusCode.UNKNOWN, "bad-txns-inputs-missingorspent", "PublishTransaction")

    monkeypatch.setattr(lnd_client, "publish_transaction", reject)
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, payout_sat=40_000,
                                   miner_fee_sat=current_miner_fee(), address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.MANUAL_REVIEW, SwapStatus.BROADCASTED})
    assert swap.status == SwapStatus.MANUAL_REVIEW
    assert "USER IS OWED" in swap.error
    payment.result(timeout=60)

    # Clean up for the following tests: actually pay this user and release the leases.
    monkeypatch.undo()
    lnd_client.publish_transaction(bytes.fromhex(swap.raw_tx), "ln2oc test cleanup")
    mine_blocks(1)
