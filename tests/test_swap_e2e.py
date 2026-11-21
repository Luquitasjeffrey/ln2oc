"""
End-to-end tests against Polar regtest. Each money-loss scenario from the security
review is reproduced by injecting an *ambiguous* failure (the call succeeds in LND
but we never learn it) and checking that the payout happens exactly once.
"""
import hashlib
import json
import os
import time

import pytest

from app.config import settings
from app.fees import current_fee_rate_sat_per_vbyte
from app.lnd import InvoiceState, LndUnavailable, lnd_client
from app.lnrpc import lightning_pb2 as ln
from app.models import SwapStatus
from app.swaps import SwapError, create_swap
from app.tx import parse_tx
from app.validator import address_to_script
from app.worker import SwapWorker
from tests.conftest import (
    bitcoin_cli, get_bitcoind_tx, get_swap, insert_swap, leases_for, mine_blocks, new_dest_address,
    received_by, send_to_kross_unconfirmed, tick_until, wait_for_status,
)

REGTEST_ADDR = "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz"


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
    # testnet4 uses the same prefixes as testnet3 (tb / 0x6f / 0xc4).
    tb = "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"
    assert address_to_script(tb, "testnet4") == address_to_script(tb, "testnet") is not None
    assert address_to_script(tb, "mainnet") is None
    assert address_to_script(tb, "signet") is None  # unknown network: nothing is valid
    # bech32 is case-insensitive: the all-uppercase form (as in QR codes) decodes the same.
    assert address_to_script(REGTEST_ADDR.upper(), "regtest") == address_to_script(REGTEST_ADDR, "regtest")


def test_new_swaps_accept_only_bech32():
    """A Lightning Address name is lowercase (LUD-16): base58 is case-sensitive, so legacy
    addresses are refused for new swaps, but still decoded for paying stored ones."""
    from app.validator import validate_bitcoin_address
    assert validate_bitcoin_address("bc1qmefue372ssa4zffa4n0hqadscqp2myg9utwrtr", "mainnet")
    assert validate_bitcoin_address("bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0", "mainnet")
    assert validate_bitcoin_address(REGTEST_ADDR.upper(), "regtest")
    for legacy in ("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"):
        assert not validate_bitcoin_address(legacy, "mainnet")
        assert address_to_script(legacy, "mainnet") is not None


@pytest.mark.asyncio
async def test_lightning_address_refuses_legacy_and_lowercases_bech32(env, client):
    legacy = bitcoin_cli("getnewaddress", "", "legacy")
    assert legacy != legacy.lower()
    for path in (f"/.well-known/lnurlp/{legacy}", f"/lnurlp/cb?btc_address={legacy}&amount={100_000 * 1000}"):
        res = await client.get(path)
        assert res.status_code == 400 and "bc1q" in res.json()["reason"], res.text
    up = REGTEST_ADDR.upper()
    data = (await client.get(f"/.well-known/lnurlp/{up}")).json()
    assert data["callback"].endswith(f"btc_address={REGTEST_ADDR}")
    assert f'"{REGTEST_ADDR}@{settings.DOMAIN}"' in data["metadata"]
    res = await client.get(f"/lnurlp/cb?btc_address={up}&amount={100_000 * 1000}")
    assert res.status_code == 200, res.text
    with env["Session"]() as db:
        from app.models import Swap
        assert db.query(Swap).filter_by(invoice=res.json()["pr"]).one().btc_address == REGTEST_ADDR


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
async def test_lightning_address_flow_as_a_wallet_does_it(env, client, payer):
    """LUD-16 + LUD-06 from the wallet's side: resolve <address>@<domain> at the
    well-known URL, check the payRequest like a wallet would, call the callback appending
    `&amount=` (plus extra params some wallets send), check the invoice amount and pay it."""
    dest = new_dest_address()
    assert dest == dest.lower()  # LUD-16: the name must be lowercase (a-z0-9-_.)
    res = await client.get(f"/.well-known/lnurlp/{dest}")
    assert res.status_code == 200, res.text
    assert res.headers["access-control-allow-origin"] == "*"  # LUD-01
    pay_request = res.json()
    assert pay_request["tag"] == "payRequest"
    assert isinstance(pay_request["minSendable"], int) and isinstance(pay_request["maxSendable"], int)
    assert 1 <= pay_request["minSendable"] <= pay_request["maxSendable"]
    assert pay_request["callback"].startswith(settings.EXTERNAL_URL.rstrip("/") + "/")
    metadata = json.loads(pay_request["metadata"])  # a JSON array sent as a raw string
    assert [v for k, v in metadata if k == "text/plain"] and len([k for k, _ in metadata if k == "text/plain"]) == 1
    assert [v for k, v in metadata if k == "text/identifier"] == [f"{dest}@{settings.DOMAIN}"]

    amount_msat = 100_000 * 1000
    callback = pay_request["callback"]
    sep = "&" if "?" in callback else "?"
    path = callback[len(settings.EXTERNAL_URL.rstrip("/")):]
    res = await client.get(f"{path}{sep}amount={amount_msat}&comment=hola&nonce=123")
    assert res.status_code == 200, res.text
    assert res.headers["access-control-allow-origin"] == "*"
    body = res.json()
    assert body.get("status") != "ERROR" and body["routes"] == []
    stub, _, _ = payer.lnd._stubs()
    decoded = stub.DecodePayReq(ln.PayReqString(pay_req=body["pr"]), timeout=10)
    assert decoded.num_msat == amount_msat  # LUD-06: the wallet checks the invoice amount
    assert decoded.destination == lnd_client.get_info().identity_pubkey

    with env["Session"]() as db:
        from app.models import Swap
        swap_id = db.query(Swap).filter_by(invoice=body["pr"]).one().id
    payment = payer.pay(body["pr"])
    swap = tick_until(env, swap_id, _DONE)
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert swap.status == SwapStatus.BROADCASTED, swap.error
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)


@pytest.mark.asyncio
async def test_lnurl_errors_carry_cors_and_reason(client):
    res = await client.get("/.well-known/lnurlp/invalid_address")
    assert res.headers["access-control-allow-origin"] == "*"
    assert res.json()["status"] == "ERROR" and res.json()["reason"]


@pytest.mark.asyncio
async def test_lnurlp_rejects_bad_amounts(client):
    base = f"/lnurlp/cb?btc_address={REGTEST_ADDR}"
    res = await client.get(f"{base}&amount=500000")
    assert res.status_code == 400 and "below minimum" in res.json()["reason"]
    res = await client.get(f"{base}&amount=60000000000")
    assert res.status_code == 400 and "exceeds maximum" in res.json()["reason"]
    res = await client.get(f"{base}&amount=100000500")
    assert res.status_code == 400 and "whole number" in res.json()["reason"]


@pytest.mark.asyncio
async def test_root_only_redirects_to_the_website(client, monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", None)
    assert (await client.get("/")).status_code == 404
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://web.example")
    for method in ("GET", "HEAD"):
        res = await client.request(method, "/", follow_redirects=False)
        assert res.status_code == 302 and res.headers["location"] == "https://web.example"
    # The service serves no frontend files at all.
    assert (await client.get("/index.html")).status_code == 404
    assert (await client.get(f"/.well-known/lnurlp/{REGTEST_ADDR}")).status_code == 200


@pytest.mark.asyncio
async def test_api_info_reports_instance_parameters(client):
    from app.info import git_commit
    res = await client.get("/api/info")
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "*"
    data = res.json()
    assert data["network"] == "regtest"
    assert data["swap_fee_rate_bps"] == round(settings.SWAP_FEE_RATE * 10_000)
    assert data["max_swap_sat"] == settings.MAX_SWAP_SAT
    assert data["fee_rate_sat_vb"] == current_fee_rate_sat_per_vbyte(lnd_client)
    assert "miner_fee_sat" not in data  # the miner fee is set when signing, never quoted
    assert data["last_payout_vbytes"] is None or 100 <= data["last_payout_vbytes"] <= 400
    assert data["commit"] == git_commit() != "unknown"
    assert data["halted"] is False


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
    assert swap.gross_sat == 100_000 - round(100_000 * settings.SWAP_FEE_RATE)  # operator: exactly the fee
    assert swap.payout_sat + swap.actual_fee_sat == swap.gross_sat
    mine_blocks(1)
    assert received_by(dest, minconf=1) == swap.payout_sat


# --------------------------------------------------------------------- polling worker


def _polling_worker(env, poll_interval: float = 0.5):
    """A real worker thread: it only learns about payments by polling LookupInvoice."""
    w = SwapWorker(session_factory=env["Session"], retry_interval_seconds=0.2,
                   poll_interval_seconds=poll_interval,
                   lock_path=str(env["tmp_path"] / "poll.lock"), on_fatal=env["fatal"])
    env["worker"] = w
    return w


def _wait_invoice_state(swap_id_or_hash, Session, state, timeout: float = 30.0):
    payment_hash = bytes.fromhex(get_swap(Session, swap_id_or_hash).payment_hash)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if lnd_client.lookup_invoice(payment_hash).state == state:
            return
        time.sleep(0.1)
    raise AssertionError(f"invoice of swap {swap_id_or_hash} never reached {state}")


_DONE = {SwapStatus.BROADCASTED, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW}


def test_polling_picks_up_payment_held_before_startup(env, payer):
    """A payment held while the service was down is seen by the first poll at startup."""
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
    payment = payer.pay(invoice)
    _wait_invoice_state(swap_id, env["Session"], InvoiceState.ACCEPTED)
    worker = _polling_worker(env, poll_interval=300)  # only the startup poll can see it
    worker.start()
    swap = wait_for_status(env["Session"], swap_id, _DONE)
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    worker.stop()
    assert not worker.is_alive()
    mine_blocks(1)


def test_polling_picks_up_new_swaps_and_expiry(env, payer):
    worker = _polling_worker(env)
    worker.start()

    # A swap created while running is noticed by the next poll once it is paid.
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
    payment = payer.pay(invoice)
    swap = wait_for_status(env["Session"], swap_id, _DONE)
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)

    # An invoice canceled/expired in LND ends as EXPIRED.
    other_id, _ = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    lnd_client.cancel_invoice(bytes.fromhex(get_swap(env["Session"], other_id).payment_hash))
    other = wait_for_status(env["Session"], other_id, {SwapStatus.EXPIRED})
    assert other.status == SwapStatus.EXPIRED
    assert not env["fatal"].reasons, env["fatal"].reasons
    worker.stop()
    mine_blocks(1)


def test_concurrent_payments_are_paid_one_after_another(env, payer):
    """Three payments held at once: one poll sees them all; the payout slot takes one and
    the others are retried at the fast pace (the next full poll is 5 minutes away)."""
    swaps = []
    for _ in range(3):
        dest = new_dest_address()
        swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
        swaps.append((swap_id, dest, invoice))
    payments = [payer.pay(invoice) for _, _, invoice in swaps]
    for swap_id, _, _ in swaps:
        _wait_invoice_state(swap_id, env["Session"], InvoiceState.ACCEPTED)
    worker = _polling_worker(env, poll_interval=300)
    worker.start()
    for i, ((swap_id, dest, _), payment) in enumerate(zip(swaps, payments)):
        swap = wait_for_status(env["Session"], swap_id, _DONE, timeout=60)
        assert swap.status == SwapStatus.BROADCASTED, swap.error
        assert payment.result(timeout=60).payment_error == "", swap.error
        assert_paid_exactly_once(swap, dest)
        # The next held payments wait for this payout to confirm: nothing checked, nothing refunded.
        time.sleep(1.5)
        for later_id, _, _ in swaps[i + 1:]:
            later = get_swap(env["Session"], later_id)
            assert later.status in (SwapStatus.PENDING, SwapStatus.SETTLING), later.status
            assert lnd_client.lookup_invoice(bytes.fromhex(later.payment_hash)).state == InvoiceState.ACCEPTED
        mine_blocks(1)
    assert not env["fatal"].reasons, env["fatal"].reasons
    worker.stop()


def test_unconfirmed_deposit_holds_payment_until_it_confirms(env, payer, monkeypatch):
    """Any wallet tx in the mempool (here an incoming deposit) postpones the payout: the
    balance is not even checked, the payment stays held, nothing is settled or refunded."""
    deposit_txid = send_to_kross_unconfirmed(0.001)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
    payment = payer.pay(invoice)
    _wait_invoice_state(swap_id, env["Session"], InvoiceState.ACCEPTED)
    assert deposit_txid in lnd_client.unconfirmed_txids(lnd_client.get_info().block_height)

    calls = []
    real_balance, real_settle = lnd_client.wallet_balance, lnd_client.settle_invoice
    monkeypatch.setattr(lnd_client, "wallet_balance", lambda: calls.append("balance") or real_balance())
    monkeypatch.setattr(lnd_client, "settle_invoice", lambda p: calls.append("settle") or real_settle(p))
    for _ in range(5):
        assert env["worker"].run_tick_guarded() is True  # blocked: retry soon
    swap = get_swap(env["Session"], swap_id)
    assert swap.status == SwapStatus.SETTLING and swap.max_miner_fee_sat is None, swap.status
    assert calls == []
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.ACCEPTED
    assert not payment.done()

    mine_blocks(1)
    swap = tick_until(env, swap_id, _DONE)
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert swap.status == SwapStatus.BROADCASTED, swap.error
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)


def test_retry_ticks_do_not_poll_every_pending_invoice(env, monkeypatch):
    for _ in range(3):
        insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    calls = {"n": 0}
    real_lookup = lnd_client.lookup_invoice

    def counting(payment_hash):
        calls["n"] += 1
        return real_lookup(payment_hash)

    monkeypatch.setattr(lnd_client, "lookup_invoice", counting)
    worker = env["worker"]
    assert worker.run_tick_guarded(poll_pending=False) is False
    assert calls["n"] == 0
    assert worker.run_tick_guarded(poll_pending=True) is False  # all OPEN: nothing to retry
    assert calls["n"] == 3  # one LookupInvoice per PENDING swap
    assert not env["fatal"].reasons, env["fatal"].reasons


def test_stop_interrupts_the_poll_wait(env):
    worker = _polling_worker(env, poll_interval=300)
    worker.start()
    t0 = time.monotonic()
    worker.stop()
    assert time.monotonic() - t0 < 5
    assert not worker.is_alive()


@pytest.mark.asyncio
async def test_pending_swaps_are_capped(env, client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_PENDING_SWAPS", 1)
    insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    res = await client.get(f"/lnurlp/cb?btc_address={REGTEST_ADDR}&amount={100_000 * 1000}")
    assert res.status_code == 503 and "Too many pending swaps" in res.json()["reason"]


# --------------------------------------------------------------------- refunds


def test_no_onchain_funds_at_payment_time_refunds_payer(env, payer):
    """Criterion: cancel the hold invoice if on-chain balance is not available."""
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=10**15, address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.FAILED, SwapStatus.BROADCASTED})
    assert not env["fatal"].reasons
    assert swap.status == SwapStatus.FAILED and "insufficient" in swap.error, swap.error
    assert swap.raw_tx is None
    assert payment.result(timeout=60).payment_error != ""  # payer got their money back
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.CANCELED
    assert leases_for(swap.lock_id) == []


def test_nothing_on_chain_happens_before_the_invoice_is_settled(env, payer, monkeypatch):
    """At ACCEPTED only the balance is checked: funding and signing only ever run with
    the invoice already SETTLED."""
    seen = []
    real_fund, real_final = lnd_client.fund_psbt, lnd_client.finalize_psbt

    def state_now():
        return lnd_client.lookup_invoice(bytes.fromhex(get_swap(env["Session"], swap_id).payment_hash)).state

    def spy_fund(**kw):
        seen.append(("fund", state_now())); return real_fund(**kw)

    def spy_final(psbt):
        seen.append(("sign", state_now())); return real_final(psbt)

    monkeypatch.setattr(lnd_client, "fund_psbt", spy_fund)
    monkeypatch.setattr(lnd_client, "finalize_psbt", spy_final)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW})
    assert payment.result(timeout=60).payment_error == ""
    assert [k for k, _ in seen] == ["fund", "sign"]
    assert all(st == InvoiceState.SETTLED for _, st in seen), seen
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)


def _pay(env, payer, gross_sat=40_000, amount_sat=50_000, until=None):
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=amount_sat, gross_sat=gross_sat, address=dest)
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, until or {SwapStatus.BROADCASTED, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW})
    return swap, payment, dest


def test_user_pays_the_real_miner_fee_operator_keeps_exactly_the_service_fee(env, payer):
    """The tx is funded paying gross to the user, then the real fee moves from our change
    to the user's output: payout + fee == gross, and the wallet spends exactly gross."""
    swap, payment, dest = _pay(env, payer)
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    assert swap.payout_sat + swap.actual_fee_sat == swap.gross_sat == 40_000
    assert swap.fee_rate_sat_vb == current_fee_rate_sat_per_vbyte(lnd_client)
    tx = parse_tx(bytes.fromhex(swap.raw_tx))
    assert len(tx.outputs) == 2
    # The fee matches the real size at the rate set when signing (LND rounds per weight unit).
    assert abs(swap.actual_fee_sat - tx.vsize * swap.fee_rate_sat_vb) <= swap.fee_rate_sat_vb
    mine_blocks(1)


def test_fee_rate_is_set_when_signing(env, payer, monkeypatch):
    """The rate is estimated at signing time, not when the swap is created."""
    import app.worker as worker_mod
    real = worker_mod.current_fee_rate_sat_per_vbyte
    calls = {"n": 0}

    def rate(lnd):
        calls["n"] += 1
        return 2 if calls["n"] >= 2 else real(lnd)  # 1st call: pre-settle check; 2nd: signing

    monkeypatch.setattr(worker_mod, "current_fee_rate_sat_per_vbyte", rate)
    swap, payment, dest = _pay(env, payer)
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    assert swap.fee_rate_sat_vb == 2
    assert swap.actual_fee_sat <= 2 * 200  # ~140 vB at 2 sat/vB; at 25 sat/vB it would be ~3.500
    assert swap.payout_sat + swap.actual_fee_sat == 40_000
    mine_blocks(1)


def test_payout_that_would_be_dust_after_mining_is_refunded_before_settle(env, payer):
    """Before settling, LND dry-runs the real tx: if the miner fee at its cap (2x the
    current estimate) could leave the payout below dust, the hold invoice is canceled
    and the payer keeps their money."""
    swap, payment, _ = _pay(env, payer, gross_sat=2_000, until={SwapStatus.FAILED, SwapStatus.BROADCASTED,
                                                                 SwapStatus.MANUAL_REVIEW})
    assert not env["fatal"].reasons
    assert swap.status == SwapStatus.FAILED and "below dust" in swap.error, swap.error
    assert payment.result(timeout=60).payment_error != ""
    assert swap.raw_tx is None and leases_for(swap.lock_id) == []


def _spike_after_settle(monkeypatch, rate_after: int, hide_size: bool):
    """Real rate for the pre-settle check, `rate_after` when signing. With hide_size the
    signing step cannot size the tx in advance, so it funds at the spiked rate and the
    fee has to be cut down to the cap afterwards."""
    import app.worker as worker_mod
    real_rate = worker_mod.current_fee_rate_sat_per_vbyte
    rate_calls = {"n": 0}

    def rate(lnd):
        rate_calls["n"] += 1
        return real_rate(lnd) if rate_calls["n"] == 1 else rate_after

    monkeypatch.setattr(worker_mod, "current_fee_rate_sat_per_vbyte", rate)
    if hide_size:
        real_size = worker_mod.SwapWorker._payout_vbytes
        size_calls = {"n": 0}

        def size(self, swap):
            size_calls["n"] += 1
            return real_size(self, swap) if size_calls["n"] == 1 else None

        monkeypatch.setattr(worker_mod.SwapWorker, "_payout_vbytes", size)


@pytest.mark.parametrize("hide_size", [False, True])
def test_fee_spike_after_settle_is_paid_up_to_the_cap(env, payer, monkeypatch, hide_size):
    """The payout pays the rate of the moment it is signed, but never more than 2x the
    miner fee estimated before settling: a spike after the settle is paid at the cap,
    no manual review."""
    _spike_after_settle(monkeypatch, rate_after=400, hide_size=hide_size)
    swap, payment, dest = _pay(env, payer, gross_sat=20_000)
    assert payment.result(timeout=60).payment_error == ""
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert_paid_exactly_once(swap, dest)
    pre_settle = current_fee_rate_sat_per_vbyte(lnd_client)
    vsize = parse_tx(bytes.fromhex(swap.raw_tx)).vsize
    # LND's dry run sizes the tx a bit conservatively (it does not know the final signatures).
    assert swap.max_miner_fee_sat <= settings.MINER_FEE_CAP_MULTIPLIER * pre_settle * (vsize + 20)
    assert swap.actual_fee_sat <= swap.max_miner_fee_sat
    assert swap.actual_fee_sat >= 0.85 * swap.max_miner_fee_sat  # paid (about) the cap, not the spike
    assert swap.fee_rate_sat_vb < 400 and swap.actual_fee_sat >= swap.fee_rate_sat_vb * vsize
    assert swap.payout_sat + swap.actual_fee_sat == 20_000
    mine_blocks(1)


def test_psbt_output_values_are_rewritten_in_place():
    from app.tx import psbt_set_output_values, psbt_unsigned_tx
    unsigned = bytes.fromhex(
        "02000000" "01" + "11" * 32 + "00000000" "00" "fdffffff"
        "02" + (1000).to_bytes(8, "little").hex() + "160014" + "22" * 20
        + (5000).to_bytes(8, "little").hex() + "160014" + "33" * 20 + "00000000")
    psbt = b"psbt\xff" + b"\x01\x00" + bytes([len(unsigned)]) + unsigned + b"\x00" + b"\x00" + b"\x00\x00"
    out = psbt_set_output_values(psbt, {0: 1200, 1: 4800})
    assert len(out) == len(psbt)
    assert [o.value for o in psbt_unsigned_tx(out).outputs] == [1200, 4800]
    with pytest.raises(ValueError):
        psbt_set_output_values(psbt, {2: 1})
    with pytest.raises(ValueError):
        psbt_unsigned_tx(b"psbu" + psbt[4:])


def test_insufficient_cltv_margin_refunds_payer(env, payer, monkeypatch):
    monkeypatch.setattr(settings, "MIN_CLTV_MARGIN_BLOCKS", 10_000)
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.FAILED, SwapStatus.BROADCASTED})
    assert swap.status == SwapStatus.FAILED and "CLTV margin" in swap.error
    assert payment.result(timeout=60).payment_error != ""


# --------------------------------------------------------------------- ambiguous failures


def test_lost_fund_response_does_not_leak_or_double_fund(env, payer, monkeypatch):
    wrapped = ambiguous_once(lnd_client.fund_psbt)
    monkeypatch.setattr(lnd_client, "fund_psbt", wrapped)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
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
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
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
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.BROADCASTED, SwapStatus.FAILED})
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert wrapped.state["calls"] == 2  # re-published the SAME stored tx
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)
    assert received_by(dest, minconf=1) == swap.payout_sat


def test_restart_mid_payout_resumes_with_new_worker(env, payer, monkeypatch):
    """Simulate a crash right after the tx was signed and stored (before broadcasting):
    a fresh worker (new process) must publish that exact tx."""
    calls = {"n": 0}
    real_publish = lnd_client.publish_transaction

    def crash_before_publish(raw, label):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LndUnavailable("injected: process died before broadcasting")
        return real_publish(raw, label)

    monkeypatch.setattr(lnd_client, "publish_transaction", crash_before_publish)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
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
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    swap = get_swap(env["Session"], swap_id)
    payment = payer.pay(invoice)
    for _ in range(40):
        if lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.ACCEPTED:
            break
        time.sleep(0.25)
    lnd_client.settle_invoice(bytes.fromhex(swap.preimage))  # someone settles behind our back
    payment.result(timeout=60)

    env["worker"].run_tick_guarded()
    assert env["fatal"].reasons and "SETTLED while swap PENDING" in env["fatal"].reasons[0]
    swap = get_swap(env["Session"], swap_id)
    assert swap.status == SwapStatus.MANUAL_REVIEW
    assert swap.raw_tx is None

    # While anything is in MANUAL_REVIEW the worker refuses to do anything else.
    env["worker"].run_tick_guarded()
    assert "MANUAL_REVIEW" in env["fatal"].reasons[-1]
    del preimage, payment_hash


def test_funding_failure_after_settle_is_fatal(env, payer, monkeypatch):
    """Once the invoice is settled the user is owed: a funding failure is never
    'refunded', it halts the service for manual resolution."""
    from app.lnd import LndError
    import grpc

    def no_funds(**kw):
        raise LndError(grpc.StatusCode.UNKNOWN, "insufficient funds available to construct transaction", "FundPsbt")

    monkeypatch.setattr(lnd_client, "fund_psbt", no_funds)
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.MANUAL_REVIEW, SwapStatus.BROADCASTED, SwapStatus.FAILED})
    assert swap.status == SwapStatus.MANUAL_REVIEW
    assert "USER IS OWED" in swap.error and swap.raw_tx is None
    assert payment.result(timeout=60).payment_error == ""  # the payer was charged
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.SETTLED


def test_publish_rejected_after_settle_is_fatal(env, payer, monkeypatch):
    from app.lnd import LndError
    import grpc

    def reject(raw, label):
        raise LndError(grpc.StatusCode.UNKNOWN, "bad-txns-inputs-missingorspent", "PublishTransaction")

    monkeypatch.setattr(lnd_client, "publish_transaction", reject)
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, {SwapStatus.MANUAL_REVIEW, SwapStatus.BROADCASTED})
    assert swap.status == SwapStatus.MANUAL_REVIEW
    assert "USER IS OWED" in swap.error
    payment.result(timeout=60)

    # Clean up for the following tests: actually pay this user and release the leases.
    monkeypatch.undo()
    lnd_client.publish_transaction(bytes.fromhex(swap.raw_tx), "ln2oc test cleanup")
    mine_blocks(1)
