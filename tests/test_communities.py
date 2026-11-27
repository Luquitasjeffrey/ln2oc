"""Communities: ?community=<name> in the LNURL-pay request, the fee split frozen on the
swap, and what is owed (SUCCESS swaps minus withdrawals). A plain wallet must see no
difference at all."""
import hashlib
import os

import pytest

from app.community import CommunityError, owed_sat, record_withdrawal, register
from app.config import Settings, settings
from app.fees import calculate_gross, split_service_fee
from app.models import Swap, SwapStatus
from tests.conftest import get_swap, mine_blocks, new_dest_address, tick_until

REGTEST_ADDR = "bcrt1qac9zasaevp62vwnnuylkm3vsy99gxahlm5n0tz"
_DONE = {SwapStatus.SUCCESS, SwapStatus.FAILED, SwapStatus.MANUAL_REVIEW}


def _community(env, name="mi-comunidad", contact="Telegram: @alguien"):
    with env["Session"]() as db:
        return register(db, name, contact).id


def _swap_row(Session, community_id, status, community_fee_sat, amount_sat=100_000):
    """A swap row in a given status, without LND: only for what is owed."""
    preimage = os.urandom(32)
    with Session() as db:
        db.add(Swap(payment_hash=hashlib.sha256(preimage).hexdigest(), preimage=preimage.hex(),
                    btc_address=REGTEST_ADDR, amount_sat=amount_sat, gross_sat=amount_sat - 700,
                    operator_fee_sat=700 - community_fee_sat, community_fee_sat=community_fee_sat,
                    community_id=community_id, invoice="lnbcrt-test", status=status))
        db.commit()


# --------------------------------------------------------------------- fee split


@pytest.mark.parametrize("amount", [1000, 1001, 1999, 100_000, 123_457, 1_000_000])
def test_fee_split_adds_up_and_rounds_for_the_house(amount):
    gross = calculate_gross(amount)
    assert split_service_fee(amount, gross, with_community=False) == (amount - gross, 0)
    operator, community = split_service_fee(amount, gross, with_community=True)
    assert community == amount * 10 // 10_000  # 0.1 %, rounded down
    assert gross + operator + community == amount


def test_fee_split_of_100k():
    assert split_service_fee(100_000, calculate_gross(100_000), True) == (600, 100)


@pytest.mark.parametrize("rate", [0.008, -0.001, 0.00015])
def test_invalid_community_fee_rate_refuses_to_start(rate):
    with pytest.raises(ValueError, match="COMMUNITY_FEE_RATE"):
        Settings(COMMUNITY_FEE_RATE=rate)


# --------------------------------------------------------------------- registry and debt


@pytest.mark.parametrize("name", ["", "MiComunidad", "mi comunidad", "a&b", "x" * 33, "ñandú"])
def test_register_rejects_invalid_names(env, name):
    with env["Session"]() as db, pytest.raises(CommunityError, match="invalid name"):
        register(db, name, "contact")


def test_register_rejects_duplicates_and_empty_contact(env):
    _community(env)
    with env["Session"]() as db:
        with pytest.raises(CommunityError, match="already exists"):
            register(db, "mi-comunidad", "otro")
        with pytest.raises(CommunityError, match="contact is required"):
            register(db, "otra", "   ")


def test_only_success_swaps_are_owed(env):
    cid = _community(env)
    other = _community(env, "otra")
    for status in SwapStatus:
        _swap_row(env["Session"], cid, status, 100)
    _swap_row(env["Session"], other, SwapStatus.SUCCESS, 50)
    _swap_row(env["Session"], None, SwapStatus.SUCCESS, 0)
    with env["Session"]() as db:
        assert owed_sat(db, cid) == 100
        assert owed_sat(db, other) == 50


def test_withdrawal_pays_what_was_shown_and_later_swaps_stay_owed(env):
    cid = _community(env)
    _swap_row(env["Session"], cid, SwapStatus.SUCCESS, 100)
    _swap_row(env["Session"], cid, SwapStatus.SUCCESS, 30)
    with env["Session"]() as db:
        shown = owed_sat(db, cid)
        assert shown == 130
        _swap_row(env["Session"], cid, SwapStatus.SUCCESS, 100)  # succeeds while the operator pays
        record_withdrawal(db, cid, shown)
        assert owed_sat(db, cid) == 100
        with pytest.raises(CommunityError, match="cannot withdraw"):
            record_withdrawal(db, cid, 101)
        with pytest.raises(CommunityError, match="cannot withdraw"):
            record_withdrawal(db, cid, 0)
        record_withdrawal(db, cid, 100)
        assert owed_sat(db, cid) == 0


# --------------------------------------------------------------------- LNURL


@pytest.mark.asyncio
async def test_plain_wallet_sees_exactly_the_same_lnurl_response(client):
    """No ?community=: the payRequest is the one every wallet got before communities."""
    res = await client.get(f"/.well-known/lnurlp/{REGTEST_ADDR}")
    assert res.status_code == 200
    base = settings.EXTERNAL_URL.rstrip("/")
    assert res.json() == {
        "tag": "payRequest",
        "callback": f"{base}/lnurlp/cb?btc_address={REGTEST_ADDR}",
        "minSendable": settings.MIN_SWAP_SAT * 1000,
        "maxSendable": settings.MAX_SWAP_SAT * 1000,
        "metadata": f'[["text/plain", "Swap out BTC to {REGTEST_ADDR}"], '
                    f'["text/identifier", "{REGTEST_ADDR}@{settings.DOMAIN}"]]',
        "commentAllowed": 0,
    }


@pytest.mark.asyncio
async def test_community_is_carried_in_the_callback_and_nothing_else_changes(env, client):
    _community(env)
    plain = (await client.get(f"/.well-known/lnurlp/{REGTEST_ADDR}")).json()
    res = await client.get(f"/.well-known/lnurlp/{REGTEST_ADDR}?community=mi-comunidad")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.pop("callback") == plain.pop("callback") + "&community=mi-comunidad"
    assert body == plain


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["no-existe", "", "Mi-Comunidad", "a%26b", "x" * 33])
async def test_unknown_or_invalid_community_is_400(env, client, name):
    _community(env)
    res = await client.get(f"/.well-known/lnurlp/{REGTEST_ADDR}?community={name}")
    assert res.status_code == 400 and "Unknown community" in res.json()["reason"]
    assert res.headers["access-control-allow-origin"] == "*"
    res = await client.get(f"/lnurlp/cb?btc_address={REGTEST_ADDR}&amount=100000000&community={name}")
    assert res.status_code == 400 and "Unknown community" in res.json()["reason"]
    with env["Session"]() as db:
        assert db.query(Swap).count() == 0


@pytest.mark.asyncio
async def test_api_info_reports_the_community_fee_rate(client):
    data = (await client.get("/api/info")).json()
    assert data["community_fee_rate_bps"] == round(settings.COMMUNITY_FEE_RATE * 10_000)


@pytest.mark.asyncio
async def test_community_swap_end_to_end_is_owed_on_success(env, client, payer):
    """A wallet following the callback of ?community=: same payout as without a
    community; the community is owed its share only once the swap is SUCCESS."""
    cid = _community(env)
    dest = new_dest_address()
    pay_request = (await client.get(f"/.well-known/lnurlp/{dest}?community=mi-comunidad")).json()
    path = pay_request["callback"][len(settings.EXTERNAL_URL.rstrip("/")):]
    res = await client.get(f"{path}&amount={100_000 * 1000}")
    assert res.status_code == 200, res.text
    with env["Session"]() as db:
        swap_id = db.query(Swap).filter_by(invoice=res.json()["pr"]).one().id
        assert owed_sat(db, cid) == 0  # issued, not paid: nothing owed
    swap = get_swap(env["Session"], swap_id)
    assert (swap.community_id, swap.gross_sat, swap.operator_fee_sat, swap.community_fee_sat) == (cid, 99_300, 600, 100)

    payment = payer.pay(swap.invoice)
    swap = tick_until(env, swap_id, _DONE)
    assert not env["fatal"].reasons, env["fatal"].reasons
    assert swap.status == SwapStatus.SUCCESS, swap.error
    assert payment.result(timeout=60).payment_error == ""
    assert swap.payout_sat + swap.actual_fee_sat == swap.gross_sat == 99_300  # the user sees no difference
    with env["Session"]() as db:
        assert owed_sat(db, cid) == 100
    mine_blocks(1)
