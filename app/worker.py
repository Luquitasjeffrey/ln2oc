"""
Swap worker: the ONLY component that moves swaps past PENDING.

Runs in a single dedicated thread, in a single process (enforced by an exclusive
file lock). Every state transition is a compare-and-set on the stored status.

Each tick:
  1. Polls the PENDING invoices (every INVOICE_POLL_INTERVAL_SECONDS): paid (ACCEPTED)
     -> INVOICE_HOLD, canceled -> EXPIRED.
  2. If the on-chain wallet has any unconfirmed tx (incoming or outgoing, our last payout
     included), does nothing else.
  3. Otherwise pays every INVOICE_HOLD swap in ONE tx (one output each), oldest first:
     - a destination already taken -> FAILED (refunded);
     - gross is accumulated while it fits the spendable balance minus ONCHAIN_RESERVE_SAT; from the first one that
       does not fit, it and every later one -> FAILED;
     - the miner fee is LND's estimate for that tx + 20 %, split equally; a payout that
       would be dust -> FAILED.
     Then settles each one, funds + signs + verifies + publishes the tx, and every swap
     paid goes to SUCCESS.

Philosophy: edge cases are NOT handled. Handling one adds code, and code adds attack
surface. Anything outside the rules above is a controlled panic: MANUAL_REVIEW, the
process stops and refuses to start until a human looks at it. An edge case gets code
only once it has actually happened. In particular, from the first settle on any failure
is fatal: the payers' money is ours and the users are owed.
"""
import fcntl
import logging
import os
import threading
import time
from typing import Callable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.halt import FatalSwapError, halt_process
from app.lnd import InvoiceState, LndClient, LndError, LndUnavailable, lnd_client
from app.models import Swap, SwapStatus
from app.tx import parse_tx
from app.validator import address_to_script

logger = logging.getLogger("ln2oc.worker")

# The users pay LND's miner fee estimate plus this margin, so any difference with the
# real tx goes to the operator, never against it.
MINER_FEE_MARGIN = 1.2
# The payout's UTXOs are leased only while it is built, signed and published (one tick).
_LEASE_SECONDS = 600


class _Blocked(Exception):
    """LND cannot answer right now (not synced). Retry later."""


class SwapWorker:
    def __init__(
        self,
        lnd: Optional[LndClient] = None,
        session_factory=None,
        retry_interval_seconds: Optional[float] = None,
        lock_path: Optional[str] = None,
        on_fatal: Optional[Callable[[str], None]] = None,
        poll_interval_seconds: Optional[float] = None,
    ):
        self.lnd = lnd or lnd_client
        self.session_factory = session_factory or SessionLocal
        self.retry_interval = retry_interval_seconds or settings.WORKER_RETRY_INTERVAL_SECONDS
        self.poll_interval = poll_interval_seconds or settings.INVOICE_POLL_INTERVAL_SECONDS
        self.lock_path = lock_path
        self.on_fatal = on_fatal or halt_process
        self._lock_fd: Optional[int] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Set by tick() when it looked up every PENDING invoice without being interrupted.
        self._poll_completed = False
        # Last "waiting" message logged, so a long wait is not logged on every retry.
        self._last_waiting: Optional[str] = None

    # ------------------------------------------------------------------ lifecycle

    def acquire_process_lock(self) -> None:
        """Exclusive, non-blocking lock: a second process (extra uvicorn worker, second
        container on the same volume, ...) fails to start instead of double-paying."""
        path = self.lock_path or settings.worker_lock_path()
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise RuntimeError(f"Another ln2oc worker holds {path}; refusing to start a second one")
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self._lock_fd = fd

    def release_process_lock(self) -> None:
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    def start(self) -> None:
        if self._lock_fd is None:
            self.acquire_process_lock()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ln2oc-swap-worker", daemon=True)
        self._thread.start()
        logger.info("Swap worker started (polling pending invoices every %.0fs)", self.poll_interval)

    def stop(self, timeout: float = 60.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                logger.error("Swap worker did not stop within %.0fs", timeout)
        self.release_process_lock()
        logger.info("Swap worker stopped")

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ loop

    def _run(self) -> None:
        """Two paces, one thread: every poll_interval look up all PENDING invoices (the
        first poll runs right away); in between, while payments are held or LND is
        unavailable, retry every retry_interval without polling PENDING."""
        next_poll = time.monotonic()
        while not self._stop.is_set():
            poll = time.monotonic() >= next_poll
            if poll:
                next_poll = time.monotonic() + self.poll_interval
            busy = self.run_tick_guarded(poll_pending=poll)
            if poll and not self._poll_completed:
                next_poll = time.monotonic()  # interrupted (e.g. LND down): poll again on the next retry
                busy = True
            wait = max(0.0, next_poll - time.monotonic())
            if busy:
                wait = min(wait, self.retry_interval)
            self._stop.wait(wait)

    def run_tick_guarded(self, poll_pending: bool = True) -> bool:
        """Runs one tick. Returns True if something needs a quick retry."""
        try:
            return self.tick(poll_pending=poll_pending)
        except FatalSwapError as e:
            self._handle_fatal(e)
        except (_Blocked, LndUnavailable) as e:
            self._log_waiting(f"LND unavailable, will retry: {e}")
        except Exception as e:
            logger.exception("Unexpected error in swap worker")
            self.on_fatal(f"unexpected error in swap worker: {e!r}")
        return True

    def _handle_fatal(self, e: FatalSwapError) -> None:
        """Controlled panic: the swaps involved go to MANUAL_REVIEW (the service refuses
        to start while one exists) and the process stops."""
        logger.critical("FATAL %s", e)
        try:
            with self.session_factory() as db:
                for swap_id in e.swap_ids:
                    swap = db.get(Swap, swap_id)
                    db.execute(update(Swap).where(Swap.id == swap_id).values(
                        status=SwapStatus.MANUAL_REVIEW, error=f"[from {swap.status.value}] {e.message}"))
                db.commit()
        except Exception:
            logger.exception("Could not flag swaps %s as MANUAL_REVIEW", e.swap_ids)
        self.on_fatal(str(e))

    def _log_waiting(self, msg: str) -> None:
        logger.log(logging.DEBUG if msg == self._last_waiting else logging.WARNING, msg)
        self._last_waiting = msg

    # ------------------------------------------------------------------ tick

    def tick(self, poll_pending: bool = True) -> bool:
        """One pass of the worker. Returning never stops the worker: _run calls tick()
        again and again until stop(). The return value only picks how soon:
          False -> nothing is held: next tick at the next poll (INVOICE_POLL_INTERVAL_SECONDS).
          True  -> payments are held waiting for the wallet: next tick in
                   WORKER_RETRY_INTERVAL_SECONDS (without polling PENDING), so they are
                   paid right after the block that unblocks them."""
        self._poll_completed = False
        with self.session_factory() as db:
            if db.execute(select(Swap.id).where(Swap.status == SwapStatus.MANUAL_REVIEW)).first():
                raise FatalSwapError(None, "a swap is in MANUAL_REVIEW; refusing to process anything")

            if poll_pending:
                pending = self._swaps(db, SwapStatus.PENDING)
                for swap in pending:
                    self._poll(db, swap)
                self._poll_completed = True
                logger.debug("Polled %d pending invoice(s)", len(pending))

            held = self._swaps(db, SwapStatus.INVOICE_HOLD)
            if not held:
                return False  # nothing to pay: no hurry, come back at the next poll
            unconfirmed = self.lnd.unconfirmed_txids(self._block_height())
            if unconfirmed:  # wallet busy: pay nothing now, retry soon
                self._log_waiting(f"{len(held)} held payment(s) waiting for {len(unconfirmed)} unconfirmed "
                                  f"wallet tx(s) to confirm ({', '.join(t[:16] for t in unconfirmed[:3])})")
                return True
            self._last_waiting = None
            self._pay(db, held)
            return False  # every held payment was paid or refunded: nothing left to hurry

    def _poll(self, db: Session, swap: Swap) -> None:
        state = self._invoice_state(swap)
        if state == InvoiceState.OPEN:
            return
        if state == InvoiceState.CANCELED:
            self._transition(db, [swap], SwapStatus.PENDING, SwapStatus.EXPIRED)
        elif state == InvoiceState.ACCEPTED:
            self._transition(db, [swap], SwapStatus.PENDING, SwapStatus.INVOICE_HOLD)
            logger.info("Swap %s: payment held (%d sat)", swap.id, swap.amount_sat)
        else:
            raise FatalSwapError(swap.id, f"invoice {InvoiceState.Name(state)} while swap PENDING")

    # ------------------------------------------------------------------ payout

    def _pay(self, db: Session, held: list[Swap]) -> None:
        """Refunds what the rules reject, then settles and pays the rest in one tx."""
        for swap in held:
            state = self._invoice_state(swap)
            if state != InvoiceState.ACCEPTED:
                raise FatalSwapError(swap.id, f"invoice {InvoiceState.Name(state)} while swap INVOICE_HOLD")

        try:
            spendable = self._spendable_sat()
        except LndError as e:
            raise FatalSwapError([s.id for s in held], f"cannot read the on-chain balance: {e}")
        taken: list[Swap] = []
        total = 0
        for i, swap in enumerate(held):
            if swap.btc_address in {s.btc_address for s in taken}:
                self._cancel_swap(db, swap, "another held payment of this payout pays the same address")
            elif total + swap.gross_sat > spendable - settings.ONCHAIN_RESERVE_SAT:
                for late in held[i:]:
                    self._cancel_swap(db, late, f"insufficient on-chain balance: {spendable} sat spendable, "
                                                f"{settings.ONCHAIN_RESERVE_SAT} sat reserve, "
                                                f"{total} sat taken by earlier payments")
                break
            else:
                taken.append(swap)
                total += swap.gross_sat

        while taken:
            try:  # e.g. "insufficient funds": the gross fits the balance, gross + miner fee does not
                est = self.lnd.estimate_tx_fee({s.btc_address: s.gross_sat for s in taken},
                                               settings.FEE_TARGET_CONF, settings.ONCHAIN_MIN_CONFS)
            except LndError as e:
                raise FatalSwapError([s.id for s in taken], f"LND cannot estimate the payout tx: {e}")
            if est.fee_sat <= 0 or est.sat_per_vbyte <= 0:
                raise FatalSwapError([s.id for s in taken], f"unusable fee estimate from LND: {est}")
            if est.sat_per_vbyte > settings.MAX_SAT_PER_VBYTE:
                for swap in taken:
                    self._cancel_swap(db, swap, f"miner fee rate {est.sat_per_vbyte} sat/vB above "
                                                f"MAX_SAT_PER_VBYTE={settings.MAX_SAT_PER_VBYTE}")
                return
            share = -(-int(est.fee_sat * MINER_FEE_MARGIN) // len(taken))  # rounded up: never against the house
            dust = [s for s in taken if s.gross_sat - share < settings.MIN_PAYOUT_SAT]
            if not dust:
                break
            for swap in dust:
                self._cancel_swap(db, swap, f"payout would be {swap.gross_sat - share} sat after a {share} sat "
                                            f"miner fee share, below dust ({settings.MIN_PAYOUT_SAT} sat)")
            taken = [s for s in taken if s not in dust]
        if not taken:
            return

        ids = [s.id for s in taken]
        owed = "; ".join(f"swap {s.id}: {s.gross_sat - share} sat to {s.btc_address}" for s in taken)
        try:
            for swap in taken:
                self.lnd.settle_invoice(bytes.fromhex(swap.preimage))
                if self._invoice_state(swap) != InvoiceState.SETTLED:
                    raise RuntimeError(f"swap {swap.id}: invoice not SETTLED right after the settle")
            payouts = {s.btc_address: s.gross_sat - share for s in taken}
            funded = self.lnd.fund_psbt(outputs=payouts, conf_target=settings.FEE_TARGET_CONF, lock_id=os.urandom(32),
                                        lock_expiration_seconds=_LEASE_SECONDS,
                                        min_confs=settings.ONCHAIN_MIN_CONFS)
            raw = bytes(self.lnd.finalize_psbt(funded.funded_psbt).raw_final_tx)
            txid, fee = self._verify(raw, funded, payouts, share * len(taken))
            logger.info("Payout tx %s (fee %d sat, %d charged), raw: %s", txid, fee, share * len(taken), raw.hex())
            error = self.lnd.publish_transaction(raw, f"ln2oc swaps {','.join(map(str, ids))}")
            if error:
                raise RuntimeError(f"publish rejected: {error}")
            self._transition(db, taken, SwapStatus.INVOICE_HOLD, SwapStatus.SUCCESS, raw_tx=raw.hex(), txid=txid,
                             actual_fee_sat=share, fee_rate_sat_vb=est.sat_per_vbyte,
                             payout_sat={s.id: payouts[s.btc_address] for s in taken})
        except Exception as e:
            raise FatalSwapError(ids, f"payout failed after settling ({e!r}). USER IS OWED: {owed}")
        logger.info("Payout %s sent: %d swap(s), %d sat to users", txid, len(taken), sum(payouts.values()))

    def _verify(self, raw: bytes, funded, payouts: dict[str, int], charged: int) -> tuple[str, int]:
        """Independent check of what LND signed: each destination exactly once with its
        payout, at most one more output (our change), inputs = the UTXOs LND leased for
        it, and a miner fee no higher than what the users were charged."""
        tx = parse_tx(raw)
        for address, payout in payouts.items():
            script = address_to_script(address, settings.BITCOIN_NETWORK)
            if [o.value for o in tx.outputs if o.script == script] != [payout]:
                raise RuntimeError(f"payout tx does not pay exactly {payout} sat once to {address}")
        if len(tx.outputs) > len(payouts) + 1:
            raise RuntimeError(f"payout tx has {len(tx.outputs)} outputs for {len(payouts)} payouts")
        leased = {(u.outpoint.txid_str, u.outpoint.output_index): u.value for u in funded.locked_utxos}
        if {(i.txid, i.vout) for i in tx.inputs} != set(leased) or len(tx.inputs) != len(leased):
            raise RuntimeError("payout tx inputs are not the UTXOs LND leased for it")
        fee = sum(leased.values()) - sum(o.value for o in tx.outputs)
        if not 0 < fee <= charged:
            raise RuntimeError(f"payout tx fee {fee} sat, users charged {charged} sat")
        return tx.txid, fee

    def _cancel_swap(self, db: Session, swap: Swap, reason: str) -> None:
        """Cancels the hold invoice: the payer keeps their sats."""
        logger.warning("Swap %s: refunding payer: %s", swap.id, reason)
        try:
            self.lnd.cancel_invoice(bytes.fromhex(swap.payment_hash))
        except LndError as e:
            raise FatalSwapError(swap.id, f"cannot cancel hold invoice: {e.message}")
        self._transition(db, [swap], SwapStatus.INVOICE_HOLD, SwapStatus.FAILED, error=reason)

    # ------------------------------------------------------------------ helpers

    def _swaps(self, db: Session, status: SwapStatus) -> list[Swap]:
        return list(db.execute(
            select(Swap).where(Swap.status == status).order_by(Swap.created_at, Swap.id)
        ).scalars())

    def _transition(self, db: Session, swaps: list[Swap], frm: SwapStatus, to: SwapStatus, **fields) -> None:
        """Compare-and-set of the swaps in ONE db transaction: all of them or none. A
        field given as a dict is set per swap id."""
        for swap in swaps:
            values = {k: v[swap.id] if isinstance(v, dict) else v for k, v in fields.items()}
            res = db.execute(update(Swap).where(Swap.id == swap.id, Swap.status == frm).values(status=to, **values))
            if res.rowcount != 1:
                db.rollback()
                raise FatalSwapError(swap.id, f"transition {frm.value} -> {to.value} lost a race")
        db.commit()
        for swap in swaps:
            db.refresh(swap)
            logger.info("Swap %s: %s -> %s", swap.id, frm.value, to.value)

    def _block_height(self) -> int:
        info = self.lnd.get_info()
        if not info.synced_to_chain:
            raise _Blocked("LND is not synced to chain")
        return int(info.block_height)

    def _invoice_state(self, swap: Swap):
        try:
            return self.lnd.lookup_invoice(bytes.fromhex(swap.payment_hash)).state
        except LndError as e:
            raise FatalSwapError(swap.id, f"cannot look up our own invoice: {e}")

    def _spendable_sat(self) -> int:
        """On-chain balance the wallet can spend now (LND keeps the anchor reserve)."""
        bal = self.lnd.wallet_balance()
        return int(bal.confirmed_balance) - int(bal.reserved_balance_anchor_chan)


swap_worker = SwapWorker()
