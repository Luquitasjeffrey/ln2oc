"""
Swap worker: the ONLY component that moves swaps past PENDING.

Runs in a single dedicated thread, in a single process (enforced by an exclusive
file lock). Every state transition is a compare-and-set on the stored status, and
every step is safe to re-run after a crash at any point.

Flow of a swap:
  1. Hold invoice ACCEPTED: the payment is held. Only the on-chain balance (and the
     HTLC's CLTV margin) is checked. Nothing is funded or signed. Not enough -> cancel
     the hold invoice right away and the payer keeps their sats.
  2. Settle the hold invoice and wait until LND reports it SETTLED. Any unexpected
     answer -> MANUAL_REVIEW.
  3. Only with the invoice SETTLED: fund + sign the payout, verify it, and store the
     raw tx in the DB BEFORE broadcasting.
  4. Broadcast the stored tx. Re-publishing that same tx is idempotent, so retries
     can never pay twice.

From step 2 on the operator holds the payer's money: any failure to pay is never
"refunded" automatically; it halts the service (MANUAL_REVIEW) for a human to fix.
"""
import fcntl
import logging
import os
import threading
from typing import Callable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.halt import FatalSwapError, halt_process
from app.invoice_watcher import InvoiceWatcher
from app.lnd import HtlcState, InvoiceState, LndClient, LndError, LndUnavailable, lnd_client
from app.models import Swap, SwapStatus
from app.tx import parse_tx
from app.validator import address_to_script

logger = logging.getLogger("ln2oc.worker")

# Statuses of a payout in flight (from the balance check to the broadcast). At most ONE
# swap may be in any of these at a time: the balance check of the next payment must see
# the wallet after the previous payout has actually spent its coins.
PAYOUT_STATUSES = (SwapStatus.SETTLING, SwapStatus.PAID, SwapStatus.SIGNED)

# Publish errors that mean "this exact tx is already known to the network".
_ALREADY_PUBLISHED_MARKERS = (
    "txn-already-in-mempool",
    "txn-already-known",
    "transaction already exists",
    "already have transaction",
    "transaction already in block chain",
)


class _Blocked(Exception):
    """A step cannot make progress right now (LND unavailable/not synced). Retry later."""


class SwapWorker:
    def __init__(
        self,
        lnd: Optional[LndClient] = None,
        session_factory=None,
        retry_interval_seconds: Optional[float] = None,
        lock_path: Optional[str] = None,
        on_fatal: Optional[Callable[[str], None]] = None,
        max_watched_invoices: Optional[int] = None,
    ):
        self.lnd = lnd or lnd_client
        self.session_factory = session_factory or SessionLocal
        self.retry_interval = retry_interval_seconds or settings.WORKER_RETRY_INTERVAL_SECONDS
        self.lock_path = lock_path
        self.on_fatal = on_fatal or halt_process
        self._lock_fd: Optional[int] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        # Wake-ups: swap ids that need a look, plus an event to interrupt the wait.
        self._wake = threading.Event()
        self._dirty: set[int] = set()
        self._dirty_lock = threading.Lock()
        self.watcher = InvoiceWatcher(
            self.lnd, on_update=self.notify,
            max_watched=max_watched_invoices or settings.MAX_WATCHED_INVOICES,
        )

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
        self._running = True
        self._watch_all_pending()
        self._thread = threading.Thread(target=self._run, name="ln2oc-swap-worker", daemon=True)
        self._thread.start()
        logger.info("Swap worker started")

    def stop(self, timeout: float = 60.0) -> None:
        self._running = False
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                logger.error("Swap worker did not stop within %.0fs", timeout)
        self.watcher.close()
        self.release_process_lock()
        logger.info("Swap worker stopped")

    # ------------------------------------------------------------------ wake-ups

    def notify(self, swap_id: int) -> None:
        """Ask the worker to look at a swap soon (called from watcher threads)."""
        with self._dirty_lock:
            self._dirty.add(swap_id)
        self._wake.set()

    def can_accept_new_swaps(self) -> bool:
        return self.watcher.has_capacity()

    def notify_new_swap(self, swap_id: int, payment_hash: bytes) -> bool:
        """Called by the API after persisting a new PENDING swap. Returns False if the
        invoice cannot be watched (it would never be noticed: caller must cancel it).
        When the worker is not running yet, start() subscribes every PENDING swap."""
        if not self._running:
            return True
        return self.watcher.watch(swap_id, payment_hash)

    def _watch_all_pending(self) -> None:
        """Startup: subscribe every PENDING swap. LND sends each invoice's current state
        first, so payments held while we were down are picked up immediately."""
        with self.session_factory() as db:
            pending = self._swaps(db, SwapStatus.PENDING)
        for swap in pending:
            if not self.watcher.watch(swap.id, bytes.fromhex(swap.payment_hash)):
                raise RuntimeError(
                    f"{len(pending)} PENDING swaps exceed MAX_WATCHED_INVOICES={self.watcher.max_watched}; "
                    "refusing to start with invoices nobody would watch"
                )
        logger.info("Subscribed to %d pending invoice(s)", len(pending))

    def _pop_dirty(self) -> set[int]:
        with self._dirty_lock:
            dirty, self._dirty = self._dirty, set()
        return dirty

    def _run(self) -> None:
        while not self._stop.is_set():
            busy = self.run_tick_guarded()
            # Idle: sleep until a watcher reports an invoice change. Busy (our own payout or
            # refund in flight, LND unavailable): retry our pending operation shortly.
            self._wake.wait(self.retry_interval if busy else None)
            self._wake.clear()  # before the next tick pops _dirty, so no notification is lost

    def run_tick_guarded(self) -> bool:
        """Runs one tick. Returns True if something needs a quick retry."""
        try:
            return self.tick()
        except FatalSwapError as e:
            self._handle_fatal(e)
        except LndUnavailable as e:
            logger.warning("LND unavailable, will retry: %s", e)
        except Exception as e:  # unknown failure: crash-safe state lets a restart resume
            logger.exception("Unexpected error in swap worker")
            self.on_fatal(f"unexpected error in swap worker: {e!r}")
        return True

    def _handle_fatal(self, e: FatalSwapError) -> None:
        logger.critical("FATAL invariant violation (%s): %s", f"swap {e.swap_id}" if e.swap_id else "global", e.message)
        if e.swap_id is not None:
            try:
                with self.session_factory() as db:
                    current = db.get(Swap, e.swap_id)
                    prev = current.status.value if current else "?"
                    db.execute(
                        update(Swap).where(Swap.id == e.swap_id).values(
                            status=SwapStatus.MANUAL_REVIEW,
                            error=f"[from {prev}] {e.message}",
                        )
                    )
                    db.commit()
            except Exception:
                logger.exception("Could not flag swap %s as MANUAL_REVIEW", e.swap_id)
        self.on_fatal(str(e))

    # ------------------------------------------------------------------ tick

    def tick(self) -> bool:
        """One pass of the state machine: in-flight refunds and payout, plus the PENDING
        swaps whose invoice a watcher reported as changed.
        Returns True if something is still in progress and needs a quick retry."""
        dirty = self._pop_dirty()
        with self.session_factory() as db:
            if db.execute(select(Swap.id).where(Swap.status == SwapStatus.MANUAL_REVIEW)).first():
                raise FatalSwapError(None, "a swap is in MANUAL_REVIEW; refusing to process anything")

            # 1. Refunds in progress.
            for swap in self._swaps(db, SwapStatus.CANCELING):
                self._do_cancel(db, swap)

            # 2. The (single) payout in flight.
            payout_busy = self._advance_payout(db)

            # 3. PENDING swaps whose invoice changed (reported by the subscriptions).
            pending = [s for s in self._swaps(db, SwapStatus.PENDING) if s.id in dirty]

            waiting = False
            for swap in pending:
                outcome = self._process_pending(db, swap, payout_busy)
                if outcome == "started":
                    payout_busy = self._advance_payout(db)
                elif outcome == "waiting":
                    waiting = True
                    with self._dirty_lock:
                        self._dirty.add(swap.id)  # payment held, payout slot busy: retry soon
                if swap.status != SwapStatus.PENDING:
                    self.watcher.unwatch(swap.id)

            return payout_busy or waiting

    def _swaps(self, db: Session, *statuses: SwapStatus) -> list[Swap]:
        return list(db.execute(
            select(Swap).where(Swap.status.in_(statuses)).order_by(Swap.created_at, Swap.id)
        ).scalars())

    def _advance_payout(self, db: Session) -> bool:
        """Advances the in-flight payout as far as possible. Returns True if a payout is
        still in flight afterwards (so no new one may start)."""
        in_flight = self._swaps(db, *PAYOUT_STATUSES)
        if len(in_flight) > 1:
            raise FatalSwapError(None, f"{len(in_flight)} payouts in flight: {[s.id for s in in_flight]}")
        if not in_flight:
            return False
        swap = in_flight[0]
        try:
            while swap.status in PAYOUT_STATUSES:
                before = swap.status
                if swap.status == SwapStatus.SETTLING:
                    self._do_settle(db, swap)
                elif swap.status == SwapStatus.PAID:
                    self._do_fund_and_sign(db, swap)
                elif swap.status == SwapStatus.SIGNED:
                    self._do_publish(db, swap)
                if swap.status == before:
                    raise FatalSwapError(swap.id, f"step for {before.value} made no progress")
        except (_Blocked, LndUnavailable) as e:
            logger.warning("Swap %s blocked in %s: %s", swap.id, swap.status.value, e)
            return True
        if swap.status == SwapStatus.CANCELING:
            self._do_cancel(db, swap)
        return False

    # ------------------------------------------------------------------ helpers

    def _transition(self, db: Session, swap: Swap, frm: SwapStatus, to: SwapStatus, **fields) -> None:
        res = db.execute(
            update(Swap).where(Swap.id == swap.id, Swap.status == frm).values(status=to, **fields)
        )
        if res.rowcount != 1:
            db.rollback()
            raise FatalSwapError(swap.id, f"transition {frm.value} -> {to.value} lost a race (rowcount={res.rowcount})")
        db.commit()
        db.refresh(swap)
        logger.info("Swap %s: %s -> %s%s", swap.id, frm.value, to.value,
                    f" ({fields['error']})" if fields.get("error") else "")

    def _to_canceling(self, db: Session, swap: Swap, reason: str) -> None:
        if swap.status not in (SwapStatus.PENDING, SwapStatus.SETTLING):
            raise FatalSwapError(swap.id, f"refusing to cancel from {swap.status.value}: {reason}")
        logger.warning("Swap %s: refunding payer: %s", swap.id, reason)
        self._transition(db, swap, swap.status, SwapStatus.CANCELING, error=reason)

    def _block_height(self) -> int:
        info = self.lnd.get_info()
        if not info.synced_to_chain:
            raise _Blocked("LND is not synced to chain")
        return int(info.block_height)

    def _check_payment(self, swap: Swap, invoice) -> int:
        """Validates a held (ACCEPTED) payment. Returns the CLTV margin in blocks."""
        expected_msat = swap.amount_sat * 1000
        if invoice.value_msat != expected_msat:
            raise FatalSwapError(swap.id, f"invoice value {invoice.value_msat} msat != swap amount {expected_msat} msat")
        held = [h for h in invoice.htlcs if h.state == HtlcState.ACCEPTED]
        held_msat = sum(h.amt_msat for h in held)
        if not held or held_msat < expected_msat or invoice.amt_paid_msat < expected_msat:
            raise FatalSwapError(
                swap.id,
                f"invoice ACCEPTED but underpaid: held {held_msat} msat, paid {invoice.amt_paid_msat} msat, "
                f"expected {expected_msat} msat",
            )
        return min(h.expiry_height for h in held) - self._block_height()

    def _lookup(self, swap: Swap):
        try:
            return self.lnd.lookup_invoice(bytes.fromhex(swap.payment_hash))
        except LndError as e:
            raise FatalSwapError(swap.id, f"cannot look up our own invoice: {e}")

    def _spendable_sat(self) -> int:
        """On-chain balance the wallet can spend now (LND already excludes leased UTXOs
        and keeps the anchor reserve unspendable)."""
        bal = self.lnd.wallet_balance()
        return int(bal.confirmed_balance) - int(bal.reserved_balance_anchor_chan)

    def _release_leases(self, swap: Swap) -> None:
        lock_id = bytes.fromhex(swap.lock_id)
        for lease in self.lnd.list_leases():
            if lease.id == lock_id:
                self.lnd.release_output(lock_id, lease.outpoint)
                logger.info("Swap %s: released lease on %s:%d", swap.id, lease.outpoint.txid_str, lease.outpoint.output_index)

    # ------------------------------------------------------------------ PENDING

    def _process_pending(self, db: Session, swap: Swap, payout_busy: bool) -> Optional[str]:
        """Returns "started" if a payout was started, "waiting" if the payment is held
        but the payout slot is busy, None otherwise."""
        invoice = self._lookup(swap)
        state = invoice.state

        if state == InvoiceState.OPEN:
            return None
        if state == InvoiceState.CANCELED:
            self._transition(db, swap, SwapStatus.PENDING, SwapStatus.EXPIRED)
            return None
        if state == InvoiceState.SETTLED:
            raise FatalSwapError(swap.id, "invoice SETTLED while swap PENDING: settled outside the payout flow")
        if state != InvoiceState.ACCEPTED:
            raise FatalSwapError(swap.id, f"unknown invoice state {state}")

        margin = self._check_payment(swap, invoice)
        if margin < settings.MIN_CLTV_MARGIN_BLOCKS:
            self._to_canceling(db, swap, f"HTLC CLTV margin {margin} < {settings.MIN_CLTV_MARGIN_BLOCKS} blocks")
            return None
        if payout_busy:
            return "waiting"  # wait for the current payout to finish
        logger.info("Swap %s: payment held (%d sat, CLTV margin %d blocks)", swap.id, swap.amount_sat, margin)
        self._transition(db, swap, SwapStatus.PENDING, SwapStatus.SETTLING)
        return "started"

    # ------------------------------------------------------------------ SETTLING

    def _do_settle(self, db: Session, swap: Swap) -> None:
        """Invoice ACCEPTED: check the on-chain balance (nothing else), then settle and
        wait until LND reports SETTLED. Re-runnable after a crash at any point."""
        invoice = self._lookup(swap)
        if invoice.state == InvoiceState.SETTLED:
            # We settled before but crashed before recording it.
            self._transition(db, swap, SwapStatus.SETTLING, SwapStatus.PAID)
            return
        if invoice.state != InvoiceState.ACCEPTED:
            # Payment no longer held (e.g. HTLC canceled by LND near expiry): nothing was taken.
            self._to_canceling(db, swap, f"payment no longer held before settle (state {invoice.state})")
            return

        margin = self._check_payment(swap, invoice)
        if margin < settings.MIN_CLTV_MARGIN_BLOCKS:
            self._to_canceling(db, swap, f"HTLC CLTV margin {margin} < {settings.MIN_CLTV_MARGIN_BLOCKS} blocks")
            return

        required = swap.payout_sat + swap.miner_fee_sat
        try:
            spendable = self._spendable_sat()
        except LndError as e:
            self._to_canceling(db, swap, f"cannot read on-chain balance: {e.message}")
            return
        if spendable < required:
            self._to_canceling(db, swap, f"insufficient on-chain balance: {spendable} sat spendable, {required} sat required")
            return

        try:
            self.lnd.settle_invoice(bytes.fromhex(swap.preimage))
        except LndError as e:
            after = self._lookup(swap)
            if after.state == InvoiceState.SETTLED:
                self._transition(db, swap, SwapStatus.SETTLING, SwapStatus.PAID)
                return
            if after.state == InvoiceState.CANCELED:
                self._to_canceling(db, swap, f"invoice canceled during settle: {e.message}")
                return
            raise FatalSwapError(swap.id, f"settle rejected while invoice {after.state}: {e.message}")

        # Wait for LND to confirm the invoice is SETTLED before touching on-chain funds.
        if self._lookup(swap).state != InvoiceState.SETTLED:
            raise _Blocked("settle sent, invoice not reported SETTLED yet")
        self._transition(db, swap, SwapStatus.SETTLING, SwapStatus.PAID)
        logger.info("Swap %s: Lightning payment settled (%d sat)", swap.id, swap.amount_sat)

    # ------------------------------------------------------------------ PAID

    def _do_fund_and_sign(self, db: Session, swap: Swap) -> None:
        """Invoice SETTLED (the payer's money is ours): fund + sign the payout, verify it
        and STORE it. Broadcasts nothing. Re-runnable: drops leases of a previous attempt.
        Any definitive failure here means the user is owed: halt for manual review."""
        if self._lookup(swap).state != InvoiceState.SETTLED:
            raise FatalSwapError(swap.id, "PAID but invoice is not SETTLED")
        self._release_leases(swap)

        lock_id = bytes.fromhex(swap.lock_id)
        owed = f"USER IS OWED {swap.payout_sat} sat to {swap.btc_address}"
        try:
            funded = self.lnd.fund_psbt(
                addr=swap.btc_address,
                amount_sat=swap.payout_sat,
                sat_per_vbyte=swap.fee_rate_sat_vb,  # the rate the user was charged for
                lock_id=lock_id,
                lock_expiration_seconds=settings.UTXO_LEASE_SECONDS,
                min_confs=settings.ONCHAIN_MIN_CONFS,
            )
        except LndError as e:
            raise FatalSwapError(swap.id, f"cannot fund payout after settle ({owed}): {e.message}")
        try:
            final = self.lnd.finalize_psbt(funded.funded_psbt)
        except LndError as e:
            raise FatalSwapError(swap.id, f"cannot sign payout after settle ({owed}): {e.message}")

        raw = bytes(final.raw_final_tx)
        txid, fee = self._verify_payout_tx(swap, raw, funded, lock_id)
        if fee > swap.miner_fee_sat:
            logger.warning("Swap %s: actual miner fee %d sat exceeds charged %d sat; operator absorbs %d sat",
                           swap.id, fee, swap.miner_fee_sat, fee - swap.miner_fee_sat)

        self._transition(db, swap, SwapStatus.PAID, SwapStatus.SIGNED,
                         raw_tx=raw.hex(), txid=txid, actual_fee_sat=fee)
        logger.info("Swap %s: payout tx %s signed and stored (fee %d sat, %d sat/vB), not broadcast yet",
                    swap.id, txid, fee, swap.fee_rate_sat_vb)

    def _verify_payout_tx(self, swap: Swap, raw: bytes, funded, lock_id: bytes) -> tuple[str, int]:
        """Independent check of what LND signed. Any surprise is fatal."""
        try:
            tx = parse_tx(raw)
        except ValueError as e:
            raise FatalSwapError(swap.id, f"cannot parse signed payout tx: {e}")

        dest_script = address_to_script(swap.btc_address, settings.BITCOIN_NETWORK)
        if dest_script is None:
            raise FatalSwapError(swap.id, f"stored address no longer validates: {swap.btc_address}")

        change_idx = funded.change_output_index
        dest_idx = [i for i, o in enumerate(tx.outputs) if o.script == dest_script]
        if len(dest_idx) != 1 or tx.outputs[dest_idx[0]].value != swap.payout_sat:
            raise FatalSwapError(swap.id, f"payout tx does not pay exactly {swap.payout_sat} sat once to destination")
        for i in range(len(tx.outputs)):
            if i != dest_idx[0] and i != change_idx:
                raise FatalSwapError(swap.id, f"payout tx has unexpected output #{i}")
        if change_idx == dest_idx[0] or len(tx.outputs) > 2:
            raise FatalSwapError(swap.id, "payout tx output layout is not [destination, change]")

        leases = [u for u in funded.locked_utxos if u.id == lock_id]
        if len(leases) != len(funded.locked_utxos):
            raise FatalSwapError(swap.id, "FundPsbt leased UTXOs under an unexpected lock id")
        leased = {(u.outpoint.txid_str, u.outpoint.output_index): u.value for u in leases}
        spent = {(i.txid, i.vout) for i in tx.inputs}
        if spent != set(leased) or len(spent) != len(tx.inputs):
            raise FatalSwapError(swap.id, "payout tx inputs do not match the UTXOs leased for this swap")

        fee = sum(leased.values()) - sum(o.value for o in tx.outputs)
        if fee <= 0:
            raise FatalSwapError(swap.id, f"payout tx has non-positive fee {fee}")
        return tx.txid, fee

    # ------------------------------------------------------------------ SIGNED

    def _do_publish(self, db: Session, swap: Swap) -> None:
        """Broadcast the stored tx. Idempotent: it is always the same signed tx."""
        if not swap.raw_tx or not swap.txid:
            raise FatalSwapError(swap.id, "SIGNED without a stored payout tx")
        raw = bytes.fromhex(swap.raw_tx)
        if parse_tx(raw).txid != swap.txid:
            raise FatalSwapError(swap.id, "stored raw tx does not match stored txid")

        invoice = self._lookup(swap)
        if invoice.state != InvoiceState.SETTLED:
            raise FatalSwapError(swap.id, f"about to broadcast but invoice is {invoice.state}, not SETTLED")

        label = f"ln2oc swap {swap.id} {swap.payment_hash[:16]}"
        try:
            publish_error = self.lnd.publish_transaction(raw, label)
        except LndError as e:
            publish_error = e.message
        if publish_error and not any(m in publish_error for m in _ALREADY_PUBLISHED_MARKERS):
            # We hold the payer's money and could not pay them. A human must act.
            raise FatalSwapError(swap.id, f"payout broadcast rejected after settle (USER IS OWED "
                                          f"{swap.payout_sat} sat, tx {swap.txid}): {publish_error}")

        self._transition(db, swap, SwapStatus.SIGNED, SwapStatus.BROADCASTED, error=None)
        logger.info("Swap %s: payout %s broadcast, %d sat to %s", swap.id, swap.txid, swap.payout_sat, swap.btc_address)

    # ------------------------------------------------------------------ CANCELING

    def _do_cancel(self, db: Session, swap: Swap) -> None:
        """Refund the payer: cancel the hold invoice, release any leased UTXOs."""
        invoice = self._lookup(swap)
        if invoice.state == InvoiceState.SETTLED:
            raise FatalSwapError(swap.id, "invoice SETTLED while CANCELING: payer charged, no payout")
        if invoice.state != InvoiceState.CANCELED:
            try:
                self.lnd.cancel_invoice(bytes.fromhex(swap.payment_hash))
            except LndError as e:
                if self._lookup(swap).state != InvoiceState.CANCELED:
                    raise FatalSwapError(swap.id, f"cannot cancel hold invoice: {e.message}")
        self._release_leases(swap)
        self._transition(db, swap, SwapStatus.CANCELING, SwapStatus.FAILED)


swap_worker = SwapWorker()
