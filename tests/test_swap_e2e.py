import asyncio
import subprocess
import pytest
from sqlalchemy import select
from app.models import Swap, SwapStatus
from app.lnd import lnd_client
from app.swaps import create_swap, SwapError, get_reserved_balance_sat
from tests.conftest import mine_blocks, get_bitcoind_tx

@pytest.mark.asyncio
async def test_lnurlp_validation_and_metadata(test_app):
    client = test_app["client"]

    # 1. Test invalid BTC address
    res = await client.get("/.well-known/lnurlp/invalid_address")
    assert res.status_code == 400
    assert res.json().get("status") == "ERROR"

    # 2. Test valid Regtest BTC address
    valid_addr = "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz"
    res = await client.get(f"/.well-known/lnurlp/{valid_addr}")
    assert res.status_code == 200
    data = res.json()
    assert data["tag"] == "payRequest"
    assert "minSendable" in data
    assert "maxSendable" in data
    assert valid_addr in data["callback"]

@pytest.mark.asyncio
async def test_lnurlp_insufficient_or_invalid_amounts(test_app):
    client = test_app["client"]
    valid_addr = "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz"

    # Amount too low (< 1000 sats -> 500 sats = 500_000 msat)
    res = await client.get(f"/lnurlp/cb?btc_address={valid_addr}&amount=500000")
    assert res.status_code == 400
    assert "below minimum" in res.json().get("reason", "")

    # Amount too high (> 50,000,000 sats)
    res = await client.get(f"/lnurlp/cb?btc_address={valid_addr}&amount=60000000000")
    assert res.status_code == 400
    assert "exceeds maximum" in res.json().get("reason", "")

@pytest.mark.asyncio
async def test_insufficient_onchain_balance(test_app, monkeypatch):
    """
    Test rejecting a swap when requested amount exceeds available on-chain balance.
    """
    session_factory = test_app["session_factory"]
    valid_addr = "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz"

    # Query current LND confirmed balance
    bal = await lnd_client.get_blockchain_balance()
    confirmed = int(bal.get("confirmed_balance", 0))

    # Temporarily set MAX_SWAP_SAT higher than confirmed balance
    from app.config import settings
    monkeypatch.setattr(settings, "MAX_SWAP_SAT", confirmed + 20_000_000)

    # Try creating swap requiring more than confirmed balance
    with session_factory() as db:
        with pytest.raises(SwapError) as exc_info:
            await create_swap(db, valid_addr, (confirmed + 10_000_000) * 1000)
        assert "Insufficient available on-chain balance" in str(exc_info.value)

@pytest.mark.asyncio
async def test_concurrent_reservations_prevent_double_spending(test_app):
    """
    Test that concurrent swaps reserve on-chain balance so that cumulative active
    swaps cannot exceed the available balance.
    """
    session_factory = test_app["session_factory"]
    valid_addr = "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz"

    with session_factory() as db:
        # Create a synthetic swap reserving almost all funds
        bal = await lnd_client.get_blockchain_balance()
        confirmed = int(bal.get("confirmed_balance", 0))
        reserved_dummy = Swap(
            payment_hash="a" * 64,
            preimage="b" * 64,
            btc_address=valid_addr,
            amount_sat=confirmed - 5000,
            payout_sat=confirmed - 6000,
            miner_fee_sat=200,
            invoice="dummy_invoice",
            status=SwapStatus.PENDING,
        )
        db.add(reserved_dummy)
        db.commit()

        # Check reserved calculation
        reserved = get_reserved_balance_sat(db)
        assert reserved == (confirmed - 6000) + 200

        # Now any swap requiring more than available (confirmed - reserved = 5800 sats) should fail
        with pytest.raises(SwapError) as exc_info:
            await create_swap(db, valid_addr, 10_000 * 1000)
        assert "Insufficient available on-chain balance" in str(exc_info.value)

@pytest.mark.asyncio
async def test_crash_recovery_settles_broadcasted_swaps(test_app, user_lnd):
    """
    Test restart recovery: if a swap is BROADCASTED (tx sent) when service starts/recovers,
    the worker must immediately settle the hold invoice and transition to SETTLED.
    """
    session_factory = test_app["session_factory"]
    worker = test_app["worker"]
    worker.session_factory = session_factory

    import os, hashlib
    preimage_bytes = os.urandom(32)
    payment_hash_bytes = hashlib.sha256(preimage_bytes).digest()

    # Create real hold invoice in LND
    inv = await lnd_client.add_hold_invoice(payment_hash_bytes, 2000, memo="recovery test")

    # Have User pay the hold invoice so it becomes ACCEPTED in LND
    async def pay_invoice():
        async with user_lnd._get_client() as user_client:
            await user_client.post(
                "/v1/channels/transactions",
                json={"payment_request": inv["payment_request"]},
                timeout=60.0
            )

    user_pay_task = asyncio.create_task(pay_invoice())

    # Wait until invoice is ACCEPTED
    for _ in range(20):
        lookup = await lnd_client.lookup_invoice(payment_hash_bytes)
        if lookup.get("state") == "ACCEPTED":
            break
        await asyncio.sleep(0.2)

    with session_factory() as db:
        swap = Swap(
            payment_hash=payment_hash_bytes.hex(),
            preimage=preimage_bytes.hex(),
            btc_address="bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz",
            amount_sat=2000,
            payout_sat=1828,
            miner_fee_sat=160,
            invoice=inv["payment_request"],
            txid="dummy_txid_already_broadcasted",
            status=SwapStatus.BROADCASTED,
        )
        db.add(swap)
        db.commit()
        swap_id = swap.id

    # Run recovery
    await worker.recover_swaps()

    with session_factory() as db:
        recovered_swap = db.execute(select(Swap).where(Swap.id == swap_id)).scalar_one()
        assert recovered_swap.status == SwapStatus.SETTLED

    # Wait for user pay task to finish
    await user_pay_task

    # Verify LND invoice is SETTLED
    lookup = await lnd_client.lookup_invoice(payment_hash_bytes)
    assert lookup.get("state") == "SETTLED"

@pytest.mark.asyncio
async def test_failed_onchain_send_cancels_hold_invoice(test_app):
    """
    Test reliability requirement: cancel Hold Invoice when the on-chain payment fails.
    """
    session_factory = test_app["session_factory"]
    worker = test_app["worker"]
    worker.session_factory = session_factory

    import os, hashlib
    preimage_bytes = os.urandom(32)
    payment_hash_bytes = hashlib.sha256(preimage_bytes).digest()

    # Create hold invoice in LND
    inv = await lnd_client.add_hold_invoice(payment_hash_bytes, 2000, memo="fail test")

    # Use an invalid address or address format that LND will reject on send_coins
    with session_factory() as db:
        swap = Swap(
            payment_hash=payment_hash_bytes.hex(),
            preimage=preimage_bytes.hex(),
            btc_address="bcrt1invalidaddressforcingfail9999",
            amount_sat=2000,
            payout_sat=1828,
            miner_fee_sat=160,
            invoice=inv["payment_request"],
            txid=None,
            status=SwapStatus.ACCEPTED,
        )
        db.add(swap)
        db.commit()
        swap_id = swap.id

    # Execute onchain send & settle
    with session_factory() as db:
        swap_to_proc = db.execute(select(Swap).where(Swap.id == swap_id)).scalar_one()
        await worker._execute_onchain_and_settle(db, swap_to_proc)

    with session_factory() as db:
        failed_swap = db.execute(select(Swap).where(Swap.id == swap_id)).scalar_one()
        assert failed_swap.status == SwapStatus.FAILED
        assert failed_swap.txid is None

    # Verify LND invoice was CANCELED
    lookup = await lnd_client.lookup_invoice(payment_hash_bytes)
    assert lookup.get("state") == "CANCELED"

@pytest.mark.asyncio
async def test_complete_e2e_swap(test_app, user_lnd):
    """
    Complete end-to-end flow:
    1. Node A (Kross) runs swapservice and has on-chain funds.
    2. LNURL-Pay request initiated for destination address.
    3. Invoice returned to User.
    4. Node B (User) pays the Hold Invoice.
    5. Swap worker detects payment ACCEPTED, broadcasts BTC on-chain.
    6. Swap worker settles the Hold Invoice.
    7. Blocks are mined, verifying received sats, txid, and settlement.
    """
    client = test_app["client"]
    worker = test_app["worker"]
    session_factory = test_app["session_factory"]
    worker.session_factory = session_factory

    # 1. Generate a new destination address on bitcoind
    cmd_addr = [
        "docker", "exec", "polar-n3-backend1",
        "bitcoin-cli", "-regtest", "-rpcuser=polaruser", "-rpcpassword=polarpass",
        "getnewaddress", "", "bech32"
    ]
    dest_address = subprocess.check_output(cmd_addr, text=True).strip()

    # 2. Call LNURL-Pay callback to create swap for 100,000 sats (100,000,000 msats)
    swap_sats = 100_000
    amount_msats = swap_sats * 1000
    res = await client.get(f"/lnurlp/cb?btc_address={dest_address}&amount={amount_msats}")
    assert res.status_code == 200, res.text
    data = res.json()
    invoice = data["pr"]
    assert invoice.startswith("lnbcrt")

    # Verify Swap in DB
    with session_factory() as db:
        swap = db.execute(select(Swap).where(Swap.invoice == invoice)).scalar_one()
        assert swap.status == SwapStatus.PENDING
        assert swap.btc_address == dest_address
        assert swap.amount_sat == swap_sats
        expected_payout = (swap_sats * 994 // 1000) - swap.miner_fee_sat
        assert swap.payout_sat == expected_payout

    # 3. Start worker
    await worker.start()

    try:
        # 4. User node pays the Hold Invoice
        async with user_lnd._get_client() as user_client:
            resp = await user_client.post(
                "/v1/channels/transactions",
                json={"payment_request": invoice},
                timeout=60.0
            )
            assert resp.status_code == 200

        # Wait for worker to detect ACCEPTED, broadcast tx and settle
        for _ in range(30):
            with session_factory() as db:
                db_swap = db.execute(select(Swap).where(Swap.invoice == invoice)).scalar_one()
                if db_swap.status == SwapStatus.SETTLED:
                    break
            await asyncio.sleep(0.5)

        with session_factory() as db:
            db_swap = db.execute(select(Swap).where(Swap.invoice == invoice)).scalar_one()
            assert db_swap.status == SwapStatus.SETTLED
            assert db_swap.txid is not None
            txid = db_swap.txid

        # 5. Mine 1 block to confirm the on-chain transaction
        mine_blocks(1)

        # 6. Verify the transaction exists in bitcoind and pays expected sats to dest_address
        tx_info = get_bitcoind_tx(txid)
        assert tx_info["txid"] == txid
        # Check outputs (vout)
        found_output = False
        for vout in tx_info["vout"]:
            val_sat = int(round(vout["value"] * 100_000_000))
            script = vout.get("scriptPubKey", {})
            if script.get("address") == dest_address:
                assert val_sat == expected_payout
                found_output = True
                break
        assert found_output, f"Destination output not found in tx {tx_info}"

        # 7. Verify LND invoice is indeed SETTLED
        payment_hash_bytes = bytes.fromhex(db_swap.payment_hash)
        lookup = await lnd_client.lookup_invoice(payment_hash_bytes)
        assert lookup.get("state") == "SETTLED"

    finally:
        await worker.stop()
