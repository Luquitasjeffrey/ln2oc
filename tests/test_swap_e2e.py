"""
End-to-end tests against Polar regtest: the swap flow, polling, refunds, the miner fee,
and the controlled panics (anything odd from the first settle on -> MANUAL_REVIEW).
More on paying several held payments together in tests/test_payout_rules.py.
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
from app.models import Swap, SwapStatus
from app.swaps import SwapError, create_swap
from app.tx import parse_tx
from app.validator import address_to_script
from app.worker import SwapWorker
from tests.conftest import (
    bitcoin_cli, get_bitcoind_tx, get_swap, insert_swap, mine_blocks, new_dest_address,
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
    assert swap.status == SwapStatus.SUCCESS, swap.error
    tx = get_bitcoind_tx(swap.txid)
    assert tx["txid"] == swap.txid == parse_tx(bytes.fromhex(swap.raw_tx)).txid
    assert received_by(dest) == swap.payout_sat  # nothing else ever paid to this address
    assert swap.payout_sat + swap.actual_fee_sat == swap.gross_sat
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.SETTLED


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
    assert swap.status == SwapStatus.SUCCESS, swap.error
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
    swap = tick_until(env, swap_id, {SwapStatus.SUCCESS, SwapStatus.FAILED})
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    assert swap.gross_sat == 100_000 - round(100_000 * settings.SWAP_FEE_RATE)  # operator: exactly the fee
    assert (swap.community_id, swap.community_fee_sat, swap.operator_fee_sat) == (None, 0, 100_000 - swap.gross_sat)
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


_DONE = {SwapStatus.SUCCESS, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW}


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


def test_concurrent_payments_are_paid_together(env, payer):
    """Three payments held at once: one poll sees them all and, the wallet being quiet,
    one tx pays them (more in tests/test_payout_rules.py)."""
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
    done = [wait_for_status(env["Session"], swap_id, _DONE, timeout=60) for swap_id, _, _ in swaps]
    for swap, (_, dest, _), payment in zip(done, swaps, payments):
        assert payment.result(timeout=60).payment_error == "", swap.error
        assert_paid_exactly_once(swap, dest)
    assert len({s.txid for s in done}) == 1
    assert not env["fatal"].reasons, env["fatal"].reasons
    worker.stop()
    mine_blocks(1)


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
    assert swap.status == SwapStatus.INVOICE_HOLD, swap.status
    assert calls == []
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.ACCEPTED
    assert not payment.done()

    mine_blocks(1)
    swap = tick_until(env, swap_id, _DONE)
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert swap.status == SwapStatus.SUCCESS, swap.error
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


# --------------------------------------------------------------------- refunds and the miner fee


def _pay(env, payer, gross_sat=40_000, amount_sat=50_000):
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=amount_sat, gross_sat=gross_sat, address=dest)
    payment = payer.pay(invoice)
    return tick_until(env, swap_id, _DONE), payment, dest


def test_no_onchain_funds_refunds_payer(env, payer):
    swap, payment, _ = _pay(env, payer, gross_sat=10**15)
    assert not env["fatal"].reasons
    assert swap.status == SwapStatus.FAILED and "insufficient" in swap.error, swap.error
    assert swap.raw_tx is None
    assert payment.result(timeout=60).payment_error != ""  # payer got their money back
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.CANCELED


def test_payout_that_would_be_dust_is_refunded(env, payer):
    swap, payment, _ = _pay(env, payer, gross_sat=2_000)  # ~140 vB x 25 sat/vB x 1.2 > 2.000
    assert not env["fatal"].reasons
    assert swap.status == SwapStatus.FAILED and "below dust" in swap.error, swap.error
    assert payment.result(timeout=60).payment_error != ""


def test_nothing_on_chain_happens_before_the_invoice_is_settled(env, payer, monkeypatch):
    seen = []
    real_fund = lnd_client.fund_psbt

    def spy_fund(**kw):
        seen.append(lnd_client.lookup_invoice(bytes.fromhex(get_swap(env["Session"], swap_id).payment_hash)).state)
        return real_fund(**kw)

    monkeypatch.setattr(lnd_client, "fund_psbt", spy_fund)
    dest = new_dest_address()
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=dest)
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, _DONE)
    assert payment.result(timeout=60).payment_error == ""
    assert seen == [InvoiceState.SETTLED]
    assert_paid_exactly_once(swap, dest)
    mine_blocks(1)


def test_user_pays_the_estimated_miner_fee_plus_margin(env, payer):
    """The user pays LND's estimate + 20 %: the real fee is always below what was
    charged, the difference stays in our change (the house)."""
    swap, payment, dest = _pay(env, payer)
    assert payment.result(timeout=60).payment_error == ""
    assert_paid_exactly_once(swap, dest)
    tx = parse_tx(bytes.fromhex(swap.raw_tx))
    vin_value = sum(round(get_bitcoind_tx(i.txid)["vout"][i.vout]["value"] * 100_000_000) for i in tx.inputs)
    real_fee = vin_value - sum(o.value for o in tx.outputs)
    # LND's estimate is already a bit above the real tx (it does not know the final signatures).
    assert 0 < real_fee < swap.actual_fee_sat <= real_fee * 1.5
    assert len(tx.outputs) == 2  # the user + our change
    mine_blocks(1)


# --------------------------------------------------------------------- controlled panics


def test_invoice_settled_outside_flow_is_fatal(env, payer):
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    swap = get_swap(env["Session"], swap_id)
    payment = payer.pay(invoice)
    _wait_invoice_state(swap_id, env["Session"], InvoiceState.ACCEPTED)
    lnd_client.settle_invoice(bytes.fromhex(swap.preimage))  # someone settles behind our back
    payment.result(timeout=60)

    env["worker"].run_tick_guarded()
    assert env["fatal"].reasons and "SETTLED while swap PENDING" in env["fatal"].reasons[0]
    swap = get_swap(env["Session"], swap_id)
    assert swap.status == SwapStatus.MANUAL_REVIEW and swap.raw_tx is None

    # While anything is in MANUAL_REVIEW the worker refuses to do anything else.
    env["worker"].run_tick_guarded()
    assert "MANUAL_REVIEW" in env["fatal"].reasons[-1]


def _set_amount(Session, swap_id: int, amount_sat: int) -> None:
    """Simulates a bug: the swap row no longer matches what its invoice was paid."""
    with Session() as db:
        db.get(Swap, swap_id).amount_sat = amount_sat
        db.commit()


@pytest.mark.parametrize("held_first", [False, True], ids=["on-detection", "before-settle"])
def test_invoice_paid_other_than_the_swap_amount_is_fatal(env, payer, held_first):
    """Defense in depth: a held payment that is not exactly the swap's amount is never
    settled nor paid out, whether it is caught when detected or right before the settle."""
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    payment = payer.pay(invoice)
    _wait_invoice_state(swap_id, env["Session"], InvoiceState.ACCEPTED)
    if held_first:  # detected while the wallet is busy, the mismatch shows up while held
        send_to_kross_unconfirmed(0.001)
        assert env["worker"].run_tick_guarded() is True
        assert get_swap(env["Session"], swap_id).status == SwapStatus.INVOICE_HOLD
        mine_blocks(1)
    _set_amount(env["Session"], swap_id, 50_001)

    swap = tick_until(env, swap_id, _DONE)
    assert env["fatal"].reasons and "paid 50000000 msat, the swap is for 50001000 msat" in env["fatal"].reasons[0]
    assert swap.status == SwapStatus.MANUAL_REVIEW and swap.raw_tx is None
    payment_hash = bytes.fromhex(swap.payment_hash)
    assert lnd_client.lookup_invoice(payment_hash).state == InvoiceState.ACCEPTED  # nothing settled
    lnd_client.cancel_invoice(payment_hash)  # the manual fix: refund the payer
    assert payment.result(timeout=60).payment_error != ""


def test_lnd_rejecting_the_fee_estimate_is_manual_review_before_settling(env, payer, monkeypatch):
    """The gross fits the balance but gross + miner fee does not: LND's EstimateFee says
    "insufficient funds". MANUAL_REVIEW (not a restart loop), nothing settled."""
    monkeypatch.setattr(SwapWorker, "_spendable_sat", lambda self: 10**15)
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=10**14, address=new_dest_address())
    payment = payer.pay(invoice)
    swap = tick_until(env, swap_id, _DONE)
    assert swap.status == SwapStatus.MANUAL_REVIEW and "cannot estimate" in swap.error, swap.error
    assert lnd_client.lookup_invoice(bytes.fromhex(swap.payment_hash)).state == InvoiceState.ACCEPTED
    lnd_client.cancel_invoice(bytes.fromhex(swap.payment_hash))  # the manual fix: refund the payer
    assert payment.result(timeout=60).payment_error != ""


class _ProcessDied(BaseException):
    """Escapes run_tick_guarded like a kill -9 would: nothing after it runs."""


def test_crash_after_the_settle_is_fatal_on_restart(env, payer, monkeypatch):
    """The process dies right after settling: on restart the swap is INVOICE_HOLD with
    its invoice SETTLED. Never assumed to be ours to resume: MANUAL_REVIEW."""
    real_settle = lnd_client.settle_invoice

    def settle_then_die(preimage):
        real_settle(preimage)
        raise _ProcessDied()

    monkeypatch.setattr(lnd_client, "settle_invoice", settle_then_die)
    swap_id, invoice = insert_swap(env["Session"], amount_sat=50_000, gross_sat=40_000, address=new_dest_address())
    payment = payer.pay(invoice)
    _wait_invoice_state(swap_id, env["Session"], InvoiceState.ACCEPTED)
    with pytest.raises(_ProcessDied):
        env["worker"].tick()
    monkeypatch.undo()

    fresh = SwapWorker(session_factory=env["Session"], lock_path=str(env["tmp_path"] / "w2.lock"),
                       on_fatal=env["fatal"])
    env["worker"] = fresh
    swap = tick_until(env, swap_id, _DONE)
    assert swap.status == SwapStatus.MANUAL_REVIEW
    assert "SETTLED while swap INVOICE_HOLD" in swap.error, swap.error
    assert payment.result(timeout=60).payment_error == ""  # the payer was charged: the user is owed


@pytest.mark.parametrize("call", ["settle_invoice", "fund_psbt", "finalize_psbt"])
def test_lost_lnd_answer_after_the_first_settle_is_fatal(env, payer, monkeypatch, call):
    """A settle is instantaneous and the payout is one step: an ambiguous answer from
    LND anywhere in it is never retried, it halts with the user owed."""
    wrapped = ambiguous_once(getattr(lnd_client, call))
    monkeypatch.setattr(lnd_client, call, wrapped)
    swap, payment, dest = _pay(env, payer)
    assert swap.status == SwapStatus.MANUAL_REVIEW and "USER IS OWED" in swap.error, swap.error
    assert wrapped.state["calls"] == 1 and swap.raw_tx is None
    assert payment.result(timeout=60).payment_error == ""
    assert received_by(dest) == 0  # nothing was published


def test_lost_publish_answer_is_fatal(env, payer, monkeypatch):
    wrapped = ambiguous_once(lnd_client.publish_transaction)
    monkeypatch.setattr(lnd_client, "publish_transaction", wrapped)
    swap, payment, dest = _pay(env, payer)
    assert swap.status == SwapStatus.MANUAL_REVIEW and "USER IS OWED" in swap.error, swap.error
    assert wrapped.state["calls"] == 1
    assert received_by(dest) > 0  # it was published: the human finds it in the log/mempool
    payment.result(timeout=60)
    mine_blocks(1)


def test_publish_rejected_is_fatal(env, payer, monkeypatch):
    from app.lnd import LndError
    import grpc
    rejected = []

    def reject(raw, label):
        rejected.append(raw)
        raise LndError(grpc.StatusCode.UNKNOWN, "bad-txns-inputs-missingorspent", "PublishTransaction")

    real_publish = lnd_client.publish_transaction
    monkeypatch.setattr(lnd_client, "publish_transaction", reject)
    swap, payment, _ = _pay(env, payer)
    assert swap.status == SwapStatus.MANUAL_REVIEW and "USER IS OWED" in swap.error, swap.error
    payment.result(timeout=60)
    real_publish(rejected[0], "ln2oc test cleanup")  # pay this user and free the leased coins
    mine_blocks(1)
