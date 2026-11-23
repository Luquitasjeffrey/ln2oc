"""
Swap worker: the ONLY component that moves swaps past PENDING.

Runs in a single dedicated thread, in a single process (enforced by an exclusive
file lock). Every state transition is a compare-and-set on the stored status, and
every step is safe to re-run after a crash at any point.

Payouts go in batches: one tx pays every swap of the batch, one output each.

Flow:
  1. Hold invoice ACCEPTED: the payment is held. While the on-chain wallet has any tx
     in the mempool (incoming or outgoing) nothing is checked: every held payment waits
     until all wallet txs confirm (only a CLTV margin running out refunds one). Then
     the held payments (oldest first, at most MAX_PAYOUT_BATCH, one per destination)
     form a batch (PENDING -> SETTLING, sharing a batch_id).
  2. Before the first settle of the batch, only the on-chain balance (and each HTLC's
     CLTV margin) is checked: a payment that does not fit is refunded, the rest of the
     batch goes on. Nothing is funded or signed.
  3. Settle each hold invoice and wait until LND reports it SETTLED. Any unexpected
     answer -> MANUAL_REVIEW.
  4. Only with every invoice of the batch SETTLED: fund + sign ONE payout tx for all of
     them, verify it, and store the raw tx in the DB (on every swap) BEFORE broadcasting.
     The miner fee is split in proportion to each user's cap (what paying them alone
     would cost), so no share passes its cap.
  5. Broadcast the stored tx. Re-publishing that same tx is idempotent, so retries
     can never pay twice.

Payment detection is synchronous polling from this same thread: every
INVOICE_POLL_INTERVAL_SECONDS it looks up each PENDING invoice, one after another
(bounded by MAX_PENDING_SWAPS). No subscriptions and no thread per invoice.

From step 3 on the operator holds the payer's money: any failure to pay is never
"refunded" automatically; it halts the service (MANUAL_REVIEW) for a human to fix.
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
from app.fees import FeeEstimateError, current_fee_rate_sat_per_vbyte
from app.halt import FatalSwapError, halt_process
from app.lnd import HtlcState, InvoiceState, LndClient, LndError, LndUnavailable, lnd_client
from app.models import Swap, SwapStatus
from app.tx import parse_tx, psbt_set_output_values, psbt_unsigned_tx
from app.validator import address_to_script

logger = logging.getLogger("ln2oc.worker")

# Statuses of a payout in flight (from the balance check to the broadcast). Only ONE
# batch may be in any of these at a time: the balance check of the next batch must see
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


def split_miner_fee(total_sat: int, caps: list[int]) -> list[int]:
    """Shares of the batch's miner fee in proportion to each user's cap. Every cap is the
    same multiple of what paying that user alone would cost now, so each one pays for
    their own payout's weight (a payout needing more inputs pays more), never above their
    cap. Integer sat: floor shares, the leftover (< n sat) one each to the largest
    remainders (oldest first on ties). Sums exactly to total_sat when the caps cover it;
    otherwise everyone pays their cap and the tx pays less (a lower rate), never the
    operator."""
    if not caps or total_sat <= 0 or any(c <= 0 for c in caps):
        raise ValueError("need a positive fee and at least one swap with a positive cap")
    cap_sum = sum(caps)
    if total_sat >= cap_sum:
        return list(caps)
    shares = [total_sat * c // cap_sum for c in caps]
    leftover = total_sat - sum(shares)
    by_remainder = sorted(range(len(caps)), key=lambda i: (-(total_sat * caps[i] % cap_sum), i))
    for i in by_remainder[:leftover]:
        shares[i] += 1  # floor < cap since total < cap_sum, so +1 never passes the cap
    return shares


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
        self._running = False
        # PENDING swaps whose payment is held (ACCEPTED) and waits for a payout batch.
        # Only touched by the worker thread (or by tests driving tick() by hand).
        self._held: set[int] = set()
        # Set by tick() when it looked up every PENDING invoice without being interrupted.
        self._poll_completed = False
        # Last "payout blocked" message logged, so a long wait is not logged every retry.
        self._last_blocked: Optional[str] = None

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
        self._thread = threading.Thread(target=self._run, name="ln2oc-swap-worker", daemon=True)
        self._thread.start()
        logger.info("Swap worker started (polling pending invoices every %.0fs)", self.poll_interval)

    def stop(self, timeout: float = 60.0) -> None:
        self._running = False
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
        first poll runs right away, so payments held while we were down are seen at
        startup); in between, while something is in flight, retry only that."""
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
                    flagged = [current] if current else []
                    if current is not None and current.batch_id:
                        # The whole batch in flight stops with it: the same tx pays all of them.
                        flagged += list(db.execute(select(Swap).where(
                            Swap.batch_id == current.batch_id, Swap.id != current.id,
                            Swap.status.in_(PAYOUT_STATUSES))).scalars())
                    for s in flagged:
                        msg = e.message if s.id == e.swap_id else f"batch halted by swap {e.swap_id}: {e.message}"
                        db.execute(update(Swap).where(Swap.id == s.id).values(
                            status=SwapStatus.MANUAL_REVIEW, error=f"[from {s.status.value}] {msg}"))
                    db.commit()
            except Exception:
                logger.exception("Could not flag swap %s as MANUAL_REVIEW", e.swap_id)
        self.on_fatal(str(e))

    # ------------------------------------------------------------------ tick

    def tick(self, poll_pending: bool = True) -> bool:
        """One pass of the state machine: in-flight refunds and payout batch, then the
        PENDING swaps: all of them (one LookupInvoice each, in creation order) when
        poll_pending, otherwise only those whose payment is already held and waits for
        a payout. Held payments form the next batch once nothing is in flight and the
        wallet has no unconfirmed tx.
        Returns True if something is still in progress and needs a quick retry."""
        self._poll_completed = False
        with self.session_factory() as db:
            if db.execute(select(Swap.id).where(Swap.status == SwapStatus.MANUAL_REVIEW)).first():
                raise FatalSwapError(None, "a swap is in MANUAL_REVIEW; refusing to process anything")

            # 1. Refunds in progress.
            for swap in self._swaps(db, SwapStatus.CANCELING):
                self._do_cancel(db, swap)

            # 2. The (single) payout batch in flight.
            payout_busy = self._advance_payout(db)

            # 3. PENDING swaps.
            pending = self._swaps(db, SwapStatus.PENDING)
            if not poll_pending:
                pending = [s for s in pending if s.id in self._held]
            held = [swap for swap in pending if self._process_pending(db, swap)]
            self._held = {s.id for s in held}

            # 4. Next batch.
            if held and not payout_busy:
                batch = self._start_batch(db, held)
                if batch:
                    self._held -= {s.id for s in batch}
                    payout_busy = self._advance_payout(db)

            if poll_pending:
                self._poll_completed = True
                logger.debug("Polled %d pending invoice(s)", len(pending))
            return payout_busy or bool(self._held)

    def _swaps(self, db: Session, *statuses: SwapStatus) -> list[Swap]:
        return list(db.execute(
            select(Swap).where(Swap.status.in_(statuses)).order_by(Swap.created_at, Swap.id)
        ).scalars())

    def _in_flight(self, db: Session) -> list[Swap]:
        """The swaps of the payout batch in flight, oldest first. Fatal if they are not
        all of one batch."""
        swaps = self._swaps(db, *PAYOUT_STATUSES)
        batches = {s.batch_id for s in swaps}
        if swaps and (len(batches) != 1 or None in batches):
            # Flag (at least) the oldest one: MANUAL_REVIEW keeps the service from starting again.
            raise FatalSwapError(swaps[0].id, f"payouts in flight are not one batch: "
                                       f"{[(s.id, s.status.value, s.batch_id) for s in swaps]}")
        return swaps

    def _log_blocked(self, msg: str) -> None:
        # Waiting for a block can last many fast retries: log each new reason once.
        logger.log(logging.DEBUG if msg == self._last_blocked else logging.WARNING, msg)
        self._last_blocked = msg

    def _start_batch(self, db: Session, held: list[Swap]) -> list[Swap]:
        """Takes held payments (oldest first) into a new batch, only with the wallet quiet:
        everything held while it had unconfirmed txs is paid in the same tx. At most
        MAX_PAYOUT_BATCH, one swap per destination (a second one waits for the next
        batch). Returns the batch (empty if the wallet is not quiet yet)."""
        try:
            unconfirmed = self.lnd.unconfirmed_txids(self._block_height())
        except _Blocked as e:
            self._log_blocked(f"{len(held)} held payment(s) waiting: {e}")
            return []
        if unconfirmed:
            self._log_blocked(f"{len(held)} held payment(s) waiting for {len(unconfirmed)} unconfirmed wallet "
                              f"tx(s) to confirm ({', '.join(t[:16] for t in unconfirmed[:3])}"
                              f"{'...' if len(unconfirmed) > 3 else ''})")
            return []
        self._last_blocked = None

        batch, destinations = [], set()
        for swap in held:
            if len(batch) >= settings.MAX_PAYOUT_BATCH:
                break
            dest = address_to_script(swap.btc_address, settings.BITCOIN_NETWORK) or swap.btc_address
            if dest in destinations:
                logger.info("Swap %s: another swap of this batch pays %s; it waits for the next batch",
                            swap.id, swap.btc_address)
                continue
            destinations.add(dest)
            batch.append(swap)
        batch_id = os.urandom(32).hex()
        self._transition_many(db, [(s, {"batch_id": batch_id}) for s in batch],
                              SwapStatus.PENDING, SwapStatus.SETTLING)
        logger.info("Batch %s: %d held payment(s) taken for one payout (swaps %s, %d sat)", batch_id[:16],
                    len(batch), [s.id for s in batch], sum(s.amount_sat for s in batch))
        return batch

    def _advance_payout(self, db: Session) -> bool:
        """Advances the batch in flight as far as possible. Returns True if a batch is
        still in flight afterwards (so no new one may start)."""
        batch: list[Swap] = []
        try:
            while True:
                batch = self._in_flight(db)
                if not batch:
                    break
                before = [(s.id, s.status) for s in batch]
                statuses = {s.status for s in batch}
                if SwapStatus.SIGNED in statuses and statuses != {SwapStatus.SIGNED}:
                    raise FatalSwapError(batch[0].id, f"batch partly signed: {before}")
                if SwapStatus.SETTLING in statuses:
                    self._do_settle(db, batch)
                elif statuses == {SwapStatus.PAID}:
                    self._do_fund_and_sign(db, batch)
                else:
                    self._do_publish(db, batch)
                if [(s.id, s.status) for s in self._in_flight(db)] == before:
                    raise FatalSwapError(batch[0].id, f"batch step made no progress: {before}")
                self._last_blocked = None
        except (_Blocked, LndUnavailable) as e:
            self._log_blocked(f"Batch {batch[0].batch_id[:16] if batch else '?'} (swaps {[(s.id, s.status.value) for s in batch]}) "
                              f"blocked: {e}")
            return True
        # Members refunded while the batch went on.
        for swap in self._swaps(db, SwapStatus.CANCELING):
            self._do_cancel(db, swap)
        return False

    # ------------------------------------------------------------------ helpers

    def _transition(self, db: Session, swap: Swap, frm: SwapStatus, to: SwapStatus, **fields) -> None:
        self._transition_many(db, [(swap, fields)], frm, to)

    def _transition_many(self, db: Session, items: list[tuple[Swap, dict]], frm: SwapStatus, to: SwapStatus) -> None:
        """Compare-and-set of several swaps in ONE db transaction: all of them or none."""
        for swap, fields in items:
            res = db.execute(
                update(Swap).where(Swap.id == swap.id, Swap.status == frm).values(status=to, **fields)
            )
            if res.rowcount != 1:
                db.rollback()
                raise FatalSwapError(swap.id, f"transition {frm.value} -> {to.value} lost a race (rowcount={res.rowcount})")
        db.commit()
        for swap, fields in items:
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

    def _release_leases(self, lock_id: bytes) -> None:
        for lease in self.lnd.list_leases():
            if lease.id == lock_id:
                self.lnd.release_output(lock_id, lease.outpoint)
                logger.info("Batch %s: released lease on %s:%d", lock_id.hex()[:16],
                            lease.outpoint.txid_str, lease.outpoint.output_index)

    def _payout_viability(self, ready: list[Swap]) -> tuple[dict[int, int], list[tuple[Swap, str]]]:
        """Last check before the batch's first settle, while every payer can still be
        refunded. Each payout pays the rate of the moment it is signed, its share capped at
        MINER_FEE_CAP_MULTIPLIER x the miner fee LND estimates now for paying it alone
        (dry run over the current wallet, nothing leased). Oldest first, a swap stays in the
        batch if its payout is above dust at its cap and the wallet still covers it (gross
        + cap) after the ones before it; then LND must be able to build the whole batch as
        one tx (newest dropped until it can). Returns ({swap id: cap}, [(refused, why)])."""
        try:
            rate = current_fee_rate_sat_per_vbyte(self.lnd)
        except FeeEstimateError as e:
            return {}, [(s, f"no usable fee estimate: {e}") for s in ready]
        try:
            spendable = self._spendable_sat()
        except LndError as e:
            return {}, [(s, f"cannot read the on-chain balance: {e.message}") for s in ready]

        caps: dict[int, int] = {}
        refused: list[tuple[Swap, str]] = []
        committed = 0
        for swap in ready:
            if address_to_script(swap.btc_address, settings.BITCOIN_NETWORK) is None:
                refused.append((swap, f"stored address no longer validates: {swap.btc_address}"))
                continue
            try:
                vbytes = self._payout_vbytes({swap.btc_address: swap.gross_sat})
            except LndError as e:
                refused.append((swap, f"cannot build the payout now: {e.message}"))
                continue
            if vbytes is None:
                refused.append((swap, "LND returned an unusable tx fee estimate"))
                continue
            miner = vbytes * rate
            cap = int(miner * settings.MINER_FEE_CAP_MULTIPLIER)
            if swap.gross_sat - cap < settings.MIN_PAYOUT_SAT:
                refused.append((swap, f"payout could be {swap.gross_sat - cap} sat with the miner fee at its cap of "
                                      f"{cap} sat ({settings.MINER_FEE_CAP_MULTIPLIER:g} x ~{miner} sat at {rate} "
                                      f"sat/vB), below dust ({settings.MIN_PAYOUT_SAT} sat)"))
                continue
            if committed + swap.gross_sat + cap > spendable:
                refused.append((swap, f"insufficient on-chain balance: {spendable - committed} sat spendable "
                                      f"after the rest of the batch, {swap.gross_sat + cap} sat required"))
                continue
            caps[swap.id] = cap
            committed += swap.gross_sat + cap

        accepted = [s for s in ready if s.id in caps]
        while len(accepted) > 1:
            try:
                if self._payout_vbytes({s.btc_address: s.gross_sat for s in accepted}) is not None:
                    break
                why = "LND returned an unusable fee estimate for the batched payout"
            except LndError as e:
                why = f"cannot build the batched payout now: {e.message}"
            last = accepted.pop()
            del caps[last.id]
            refused.append((last, why))
        return caps, refused

    def _payout_vbytes(self, outputs: dict[str, int]) -> Optional[int]:
        """Approximate size of a payout tx paying `outputs` as LND would build it now (dry
        run, no leases)."""
        est = self.lnd.estimate_tx_fee(outputs, settings.FEE_TARGET_CONF, settings.ONCHAIN_MIN_CONFS)
        if est.fee_sat <= 0 or est.sat_per_vbyte <= 0:
            return None
        return -(-est.fee_sat // est.sat_per_vbyte)  # rounded up

    @staticmethod
    def _owed(batch: list[Swap]) -> str:
        return "USER IS OWED: " + "; ".join(
            f"swap {s.id}: {s.gross_sat} sat minus miner fee to {s.btc_address}" for s in batch)

    # ------------------------------------------------------------------ PENDING

    def _process_pending(self, db: Session, swap: Swap) -> bool:
        """Returns True if the payment is held (ACCEPTED, enough CLTV margin) and waits
        for a payout batch."""
        invoice = self._lookup(swap)
        state = invoice.state

        if state == InvoiceState.OPEN:
            return False
        if state == InvoiceState.CANCELED:
            self._transition(db, swap, SwapStatus.PENDING, SwapStatus.EXPIRED)
            return False
        if state == InvoiceState.SETTLED:
            raise FatalSwapError(swap.id, "invoice SETTLED while swap PENDING: settled outside the payout flow")
        if state != InvoiceState.ACCEPTED:
            raise FatalSwapError(swap.id, f"unknown invoice state {state}")

        margin = self._check_payment(swap, invoice)
        if margin < settings.MIN_CLTV_MARGIN_BLOCKS:
            self._to_canceling(db, swap, f"HTLC CLTV margin {margin} < {settings.MIN_CLTV_MARGIN_BLOCKS} blocks")
            return False
        if swap.id not in self._held:
            logger.info("Swap %s: payment held (%d sat, CLTV margin %d blocks)", swap.id, swap.amount_sat, margin)
        return True

    # ------------------------------------------------------------------ SETTLING

    def _do_settle(self, db: Session, batch: list[Swap]) -> None:
        """Batch with swaps in SETTLING (the rest PAID). Before its first settle: wait until
        the wallet has no unconfirmed tx and check the on-chain balance for the whole batch
        (nothing else), refunding what does not fit. Then settle each invoice and wait
        until LND reports it SETTLED. Re-runnable after a crash at any point: once any swap
        of the batch is settled, the rest are settled without re-checking (the batch was
        checked as a whole before the first settle)."""
        ready = []
        for swap in [s for s in batch if s.status == SwapStatus.SETTLING]:
            invoice = self._lookup(swap)
            if invoice.state == InvoiceState.SETTLED:
                # We settled before but crashed before recording it.
                self._transition(db, swap, SwapStatus.SETTLING, SwapStatus.PAID)
                continue
            if invoice.state != InvoiceState.ACCEPTED:
                # Payment no longer held (e.g. HTLC canceled by LND near expiry): nothing was taken.
                self._to_canceling(db, swap, f"payment no longer held before settle (state {invoice.state})")
                continue
            margin = self._check_payment(swap, invoice)
            if margin < settings.MIN_CLTV_MARGIN_BLOCKS:
                self._to_canceling(db, swap, f"HTLC CLTV margin {margin} < {settings.MIN_CLTV_MARGIN_BLOCKS} blocks")
                continue
            ready.append(swap)
        if not ready:
            return

        if any(s.status == SwapStatus.PAID for s in batch):
            missing = [s.id for s in ready if not s.max_miner_fee_sat or s.max_miner_fee_sat <= 0]
            if missing:
                raise FatalSwapError(missing[0], f"batch partly settled but swaps {missing} have no miner fee cap")
        else:
            # With any wallet tx in the mempool (a deposit, a channel tx) the balance and
            # the coin selection are not settled yet: check nothing and cancel nothing, just
            # keep the payments held and retry. Only the CLTV margin above can end the wait.
            unconfirmed = self.lnd.unconfirmed_txids(self._block_height())
            if unconfirmed:
                raise _Blocked(f"waiting for {len(unconfirmed)} unconfirmed wallet tx(s) to confirm "
                               f"({', '.join(t[:16] for t in unconfirmed[:3])}{'...' if len(unconfirmed) > 3 else ''})")
            caps, refused = self._payout_viability(ready)
            for swap, reason in refused:
                self._to_canceling(db, swap, reason)
            ready = [s for s in ready if s.id in caps]
            if not ready:
                return
            # Persist the caps before settling: after the settle they bound each user's miner fee.
            for swap in ready:
                db.execute(update(Swap).where(Swap.id == swap.id, Swap.status == SwapStatus.SETTLING)
                           .values(max_miner_fee_sat=caps[swap.id]))
            db.commit()
            for swap in ready:
                db.refresh(swap)

        for swap in ready:
            self._settle(db, swap)

        # Wait for LND to confirm each invoice is SETTLED before touching on-chain funds.
        for swap in ready:
            if swap.status != SwapStatus.SETTLING:
                continue
            if self._lookup(swap).state != InvoiceState.SETTLED:
                raise _Blocked(f"swap {swap.id}: settle sent, invoice not reported SETTLED yet")
            self._transition(db, swap, SwapStatus.SETTLING, SwapStatus.PAID)
            logger.info("Swap %s: Lightning payment settled (%d sat)", swap.id, swap.amount_sat)

    def _settle(self, db: Session, swap: Swap) -> None:
        try:
            self.lnd.settle_invoice(bytes.fromhex(swap.preimage))
        except LndError as e:
            after = self._lookup(swap)
            if after.state == InvoiceState.SETTLED:
                return
            if after.state == InvoiceState.CANCELED:
                self._to_canceling(db, swap, f"invoice canceled during settle: {e.message}")
                return
            raise FatalSwapError(swap.id, f"settle rejected while invoice {after.state}: {e.message}")

    # ------------------------------------------------------------------ PAID

    def _do_fund_and_sign(self, db: Session, batch: list[Swap]) -> None:
        """Every invoice of the batch SETTLED (the payers' money is ours): fund + sign ONE
        payout tx paying each of them, verify it and STORE it on every swap. Broadcasts
        nothing. Re-runnable: drops leases of a previous attempt. Any definitive failure
        here means the users are owed: halt for manual review."""
        lead = batch[0].id
        for swap in batch:
            if self._lookup(swap).state != InvoiceState.SETTLED:
                raise FatalSwapError(swap.id, "PAID but invoice is not SETTLED")
        lock_id = bytes.fromhex(batch[0].batch_id)
        self._release_leases(lock_id)

        owed = self._owed(batch)
        scripts: dict[int, bytes] = {}
        for swap in batch:
            if not swap.max_miner_fee_sat or swap.max_miner_fee_sat <= 0:
                raise FatalSwapError(swap.id, f"PAID without a miner fee cap ({owed})")
            script = address_to_script(swap.btc_address, settings.BITCOIN_NETWORK)
            if script is None:
                raise FatalSwapError(swap.id, f"stored address no longer validates: {swap.btc_address} ({owed})")
            if script in scripts.values():
                raise FatalSwapError(swap.id, f"two swaps of the batch pay the same destination ({owed})")
            scripts[swap.id] = script
        gross = {s.btc_address: s.gross_sat for s in batch}
        if len(gross) != len(batch):
            raise FatalSwapError(lead, f"two swaps of the batch pay the same address ({owed})")
        total_cap = sum(s.max_miner_fee_sat for s in batch)

        # The rate is the one of this moment; the fee never exceeds the caps set before settling.
        try:
            rate = current_fee_rate_sat_per_vbyte(self.lnd)
        except FeeEstimateError as e:
            rate = None
            logger.warning("Batch %s: no usable fee estimate at payout (%s); paying the caps", lock_id.hex()[:16], e)
        try:
            vbytes = self._payout_vbytes(gross)
        except LndError:
            vbytes = None
        if vbytes:
            cap_rate = max(settings.MIN_SAT_PER_VBYTE, total_cap // vbytes)
            rate = cap_rate if rate is None else min(rate, cap_rate)
        elif rate is None:
            raise FatalSwapError(lead, f"no fee rate and no tx size to pay the payout with ({owed})")

        funded = self._fund(lead, gross, rate, lock_id, owed)
        psbt, payouts = self._deduct_fee(batch, scripts, funded, owed)
        exact = psbt is not None
        if not exact:
            # No change output to take the fees from: fund the net amounts instead. The new
            # tx can weigh slightly differently; that difference is the operator's (logged).
            self._release_leases(lock_id)
            funded = self._fund(lead, {s.btc_address: payouts[s.id] for s in batch}, rate, lock_id, owed)
            psbt = funded.funded_psbt
        try:
            final = self.lnd.finalize_psbt(psbt)
        except LndError as e:
            raise FatalSwapError(lead, f"cannot sign payout after settle ({owed}): {e.message}")

        raw = bytes(final.raw_final_tx)
        txid, fee = self._verify_payout_tx(batch, scripts, raw, funded, lock_id, payouts)
        charged = sum(s.gross_sat - payouts[s.id] for s in batch)
        if exact and fee != charged:
            raise FatalSwapError(lead, f"payout tx fee {fee} != {charged} charged to the users ({owed})")
        if not exact:
            logger.warning("Batch %s: no change output; users charged %d sat, tx fee %d sat (caps %d)",
                           lock_id.hex()[:16], charged, fee, total_cap)
        vsize = parse_tx(raw).vsize
        if fee < vsize * settings.MIN_SAT_PER_VBYTE:
            raise FatalSwapError(lead, f"payout tx fee {fee} sat is below {settings.MIN_SAT_PER_VBYTE} sat/vB "
                                       f"for {vsize} vB ({owed})")

        if fee < vsize * rate:  # capped: record the rate the tx actually pays
            rate = fee // vsize
        self._transition_many(db, [
            (s, dict(raw_tx=raw.hex(), txid=txid, payout_sat=payouts[s.id],
                     actual_fee_sat=s.gross_sat - payouts[s.id], fee_rate_sat_vb=rate))
            for s in batch
        ], SwapStatus.PAID, SwapStatus.SIGNED)
        logger.info("Batch %s: payout tx %s signed and stored (%d swap(s), %d sat to users, fee %d sat at %d sat/vB), "
                    "not broadcast yet", lock_id.hex()[:16], txid, len(batch), sum(payouts.values()), fee, rate)

    def _fund(self, lead: int, outputs: dict[str, int], rate: int, lock_id: bytes, owed: str):
        try:
            return self.lnd.fund_psbt(
                outputs=outputs,
                sat_per_vbyte=rate,
                lock_id=lock_id,
                lock_expiration_seconds=settings.UTXO_LEASE_SECONDS,
                min_confs=settings.ONCHAIN_MIN_CONFS,
            )
        except LndError as e:
            raise FatalSwapError(lead, f"cannot fund payout after settle ({owed}): {e.message}")

    def _deduct_fee(self, batch: list[Swap], scripts: dict[int, bytes], funded, owed: str
                    ) -> tuple[Optional[bytes], dict[int, int]]:
        """The tx was funded paying each gross_sat to its user, so the miner fee came out of
        our change. Charge it to the users instead, in proportion to their caps, each never
        above that user's cap: destination = gross - share, change gets the rest (Σinputs - Σgross).
        Only amounts change, so the tx size stays the same; the operator keeps exactly the
        service fees. Returns (None, payouts) if there is no change output to rebalance."""
        lead = batch[0].id
        try:
            tx = psbt_unsigned_tx(funded.funded_psbt)
        except ValueError as e:
            raise FatalSwapError(lead, f"cannot read funded PSBT ({owed}): {e}")
        dest: dict[int, int] = {}
        for swap in batch:
            idx = [i for i, o in enumerate(tx.outputs) if o.script == scripts[swap.id]]
            if len(idx) != 1 or tx.outputs[idx[0]].value != swap.gross_sat:
                raise FatalSwapError(swap.id, f"funded PSBT does not pay {swap.gross_sat} sat once to "
                                              f"{swap.btc_address} ({owed})")
            dest[swap.id] = idx[0]
        funded_fee = sum(u.value for u in funded.locked_utxos) - sum(o.value for o in tx.outputs)
        if funded_fee <= 0:
            raise FatalSwapError(lead, f"funded PSBT has non-positive fee {funded_fee} ({owed})")
        fees = split_miner_fee(funded_fee, [s.max_miner_fee_sat for s in batch])
        if sum(fees) < funded_fee:
            logger.warning("Batch %s: miner fee %d sat capped at %d sat (shares %s)",
                           batch[0].batch_id[:16], funded_fee, sum(fees), fees)
        payouts: dict[int, int] = {}
        for swap, fee in zip(batch, fees):
            payout = swap.gross_sat - fee
            if payout < settings.MIN_PAYOUT_SAT:  # cannot happen: checked against the cap before settling
                raise FatalSwapError(swap.id, f"miner fee {fee} sat leaves a {payout} sat payout, below dust ({owed})")
            payouts[swap.id] = payout
        c = funded.change_output_index
        if c < 0 or c in dest.values() or c >= len(tx.outputs):
            return None, payouts
        values = {dest[s.id]: payouts[s.id] for s in batch}
        values[c] = tx.outputs[c].value + funded_fee  # change = Σin - Σgross
        try:
            psbt = psbt_set_output_values(funded.funded_psbt, values)
        except ValueError as e:
            raise FatalSwapError(lead, f"cannot adjust funded PSBT ({owed}): {e}")
        return psbt, payouts

    def _verify_payout_tx(self, batch: list[Swap], scripts: dict[int, bytes], raw: bytes, funded,
                          lock_id: bytes, payouts: dict[int, int]) -> tuple[str, int]:
        """Independent check of what LND signed: exactly one output per swap with its
        payout, at most one more (our change), inputs = the UTXOs leased for this batch.
        Any surprise is fatal."""
        lead = batch[0].id
        try:
            tx = parse_tx(raw)
        except ValueError as e:
            raise FatalSwapError(lead, f"cannot parse signed payout tx: {e}")

        dest_idx = set()
        for swap in batch:
            idx = [i for i, o in enumerate(tx.outputs) if o.script == scripts[swap.id]]
            if len(idx) != 1 or tx.outputs[idx[0]].value != payouts[swap.id]:
                raise FatalSwapError(swap.id, f"payout tx does not pay exactly {payouts[swap.id]} sat once to "
                                              f"{swap.btc_address}")
            dest_idx.add(idx[0])
        change_idx = funded.change_output_index
        if change_idx in dest_idx:
            raise FatalSwapError(lead, "payout tx change output is a destination")
        others = [i for i in range(len(tx.outputs)) if i not in dest_idx]
        if len(others) > 1 or any(i != change_idx for i in others):
            raise FatalSwapError(lead, f"payout tx has unexpected output(s) {others}")

        leases = [u for u in funded.locked_utxos if u.id == lock_id]
        if len(leases) != len(funded.locked_utxos):
            raise FatalSwapError(lead, "FundPsbt leased UTXOs under an unexpected lock id")
        leased = {(u.outpoint.txid_str, u.outpoint.output_index): u.value for u in leases}
        spent = {(i.txid, i.vout) for i in tx.inputs}
        if spent != set(leased) or len(spent) != len(tx.inputs):
            raise FatalSwapError(lead, "payout tx inputs do not match the UTXOs leased for this batch")

        fee = sum(leased.values()) - sum(o.value for o in tx.outputs)
        if fee <= 0:
            raise FatalSwapError(lead, f"payout tx has non-positive fee {fee}")
        return tx.txid, fee

    # ------------------------------------------------------------------ SIGNED

    def _do_publish(self, db: Session, batch: list[Swap]) -> None:
        """Broadcast the stored tx. Idempotent: it is always the same signed tx."""
        lead = batch[0]
        if len({(s.raw_tx, s.txid) for s in batch}) != 1 or not lead.raw_tx or not lead.txid:
            raise FatalSwapError(lead.id, "SIGNED batch without one stored payout tx")
        raw = bytes.fromhex(lead.raw_tx)
        tx = parse_tx(raw)
        if tx.txid != lead.txid:
            raise FatalSwapError(lead.id, "stored raw tx does not match stored txid")
        for swap in batch:
            script = address_to_script(swap.btc_address, settings.BITCOIN_NETWORK)
            outs = [o for o in tx.outputs if o.script == script]
            if script is None or len(outs) != 1 or outs[0].value != swap.payout_sat:
                raise FatalSwapError(swap.id, f"stored payout tx does not pay {swap.payout_sat} sat once to "
                                              f"{swap.btc_address}")
            invoice = self._lookup(swap)
            if invoice.state != InvoiceState.SETTLED:
                raise FatalSwapError(swap.id, f"about to broadcast but invoice is {invoice.state}, not SETTLED")

        label = f"ln2oc batch {lead.batch_id[:16]} swaps {','.join(str(s.id) for s in batch)}"
        try:
            publish_error = self.lnd.publish_transaction(raw, label)
        except LndError as e:
            publish_error = e.message
        if publish_error and not any(m in publish_error for m in _ALREADY_PUBLISHED_MARKERS):
            # We hold the payers' money and could not pay them. A human must act.
            owed = "; ".join(f"swap {s.id}: {s.payout_sat} sat to {s.btc_address}" for s in batch)
            raise FatalSwapError(lead.id, f"payout broadcast rejected after settle (USER IS OWED: {owed}; "
                                          f"tx {lead.txid}): {publish_error}")

        self._transition_many(db, [(s, {"error": None}) for s in batch], SwapStatus.SIGNED, SwapStatus.BROADCASTED)
        logger.info("Batch %s: payout %s broadcast, %d swap(s), %d sat to users", lead.batch_id[:16], lead.txid,
                    len(batch), sum(s.payout_sat for s in batch))

    # ------------------------------------------------------------------ CANCELING

    def _do_cancel(self, db: Session, swap: Swap) -> None:
        """Refund the payer: cancel the hold invoice. Nothing on-chain to undo: UTXOs are
        only leased once every invoice of a batch is settled, never for a refunded swap."""
        invoice = self._lookup(swap)
        if invoice.state == InvoiceState.SETTLED:
            raise FatalSwapError(swap.id, "invoice SETTLED while CANCELING: payer charged, no payout")
        if invoice.state != InvoiceState.CANCELED:
            try:
                self.lnd.cancel_invoice(bytes.fromhex(swap.payment_hash))
            except LndError as e:
                if self._lookup(swap).state != InvoiceState.CANCELED:
                    raise FatalSwapError(swap.id, f"cannot cancel hold invoice: {e.message}")
        self._transition(db, swap, SwapStatus.CANCELING, SwapStatus.FAILED)


swap_worker = SwapWorker()
