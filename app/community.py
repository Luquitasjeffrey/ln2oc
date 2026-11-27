"""Communities: Lightning services that send us their users (?community=<name> in the
LNURL-pay request) and are owed a share of the service fee of every SUCCESS swap.

Nothing here moves money: the operator pays each community by hand and records it as a
withdrawal. What is owed is derived from the swaps, never kept as a counter:

    owed = sum(community_fee_sat of its SUCCESS swaps) - sum(its withdrawals)

so the worker never touches communities, and a swap resolved by hand to SUCCESS counts."""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Community, CommunityWithdrawal, Swap, SwapStatus

# Goes into URLs as is: lowercase like a Lightning Address name, nothing to escape.
NAME_RULE = "1-32 characters: a-z, 0-9 and '-'"
_NAME_RE = re.compile(r"[a-z0-9-]{1,32}")


class CommunityError(Exception):
    pass


def valid_name(name: str) -> bool:
    return _NAME_RE.fullmatch(name) is not None


def get_by_name(db: Session, name: str) -> Community | None:
    if not valid_name(name):
        return None
    return db.execute(select(Community).where(Community.name == name)).scalar_one_or_none()


def register(db: Session, name: str, contact: str) -> Community:
    if not valid_name(name):
        raise CommunityError(f"invalid name {name!r} ({NAME_RULE})")
    contact = contact.strip()
    if not contact:
        raise CommunityError("contact is required")
    if get_by_name(db, name) is not None:
        raise CommunityError(f"community {name!r} already exists")
    community = Community(name=name, contact=contact)
    db.add(community)
    db.commit()
    db.refresh(community)
    return community


def owed_sat(db: Session, community_id: int) -> int:
    earned = db.execute(select(func.coalesce(func.sum(Swap.community_fee_sat), 0)).where(
        Swap.community_id == community_id, Swap.status == SwapStatus.SUCCESS)).scalar_one()
    paid = db.execute(select(func.coalesce(func.sum(CommunityWithdrawal.amount_sat), 0)).where(
        CommunityWithdrawal.community_id == community_id)).scalar_one()
    owed = earned - paid
    if owed < 0:
        raise CommunityError(f"community {community_id}: paid {paid} sat, more than the {earned} sat earned")
    return owed


def record_withdrawal(db: Session, community_id: int, amount_sat: int) -> CommunityWithdrawal:
    """Records that the operator pays amount_sat to the community: the amount shown to
    them, not "everything": a swap that succeeds meanwhile stays owed."""
    owed = owed_sat(db, community_id)
    if not (0 < amount_sat <= owed):
        raise CommunityError(f"cannot withdraw {amount_sat} sat: {owed} sat owed")
    w = CommunityWithdrawal(community_id=community_id, amount_sat=amount_sat)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w
