"""
Event source for the swap worker: one SubscribeSingleInvoice stream per PENDING swap.

This is the ONLY way the worker learns about invoice changes. No events are lost:
on every (re)subscription LND first sends the invoice's current state, so a payment
held while we were down or while a stream was broken is seen on reconnect.

Watchers NEVER touch the database or make decisions. They only tell the worker
"look at swap X now"; the worker re-reads the invoice from LND and applies the
state machine as usual, so duplicated notifications are harmless.
"""
import logging
import threading
from typing import Callable

import grpc

from app.lnd import InvoiceState, LndClient

logger = logging.getLogger("ln2oc.watcher")

# Once the invoice reaches one of these, the worker owns the swap; stop watching.
_FINAL_FOR_WATCHER = (InvoiceState.ACCEPTED, InvoiceState.CANCELED, InvoiceState.SETTLED)

_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX = 30.0

# Each watcher thread just blocks on a gRPC stream; keep their stacks small.
_WATCHER_STACK_SIZE = 256 * 1024


class InvoiceWatcher:
    def __init__(self, lnd: LndClient, on_update: Callable[[int], None], max_watched: int):
        self.lnd = lnd
        self.on_update = on_update
        self.max_watched = max_watched
        self._lock = threading.Lock()
        self._threads: dict[int, threading.Thread] = {}
        self._calls: dict[int, object] = {}
        self._stopping: set[int] = set()
        self._closed = False

    def watched_count(self) -> int:
        with self._lock:
            return len(self._threads)

    def has_capacity(self) -> bool:
        with self._lock:
            return not self._closed and len(self._threads) < self.max_watched

    def is_watching(self, swap_id: int) -> bool:
        with self._lock:
            return swap_id in self._threads

    def watch(self, swap_id: int, payment_hash: bytes) -> bool:
        """Starts a subscription for this swap unless already watched. Returns False if
        it could not be watched (closed, or over capacity)."""
        with self._lock:
            if swap_id in self._threads:
                return True
            if self._closed or len(self._threads) >= self.max_watched:
                return False
            previous = threading.stack_size(_WATCHER_STACK_SIZE)
            try:
                t = threading.Thread(target=self._run, args=(swap_id, payment_hash),
                                     name=f"ln2oc-watch-{swap_id}", daemon=True)
                self._threads[swap_id] = t
                t.start()
            finally:
                threading.stack_size(previous)
            return True

    def unwatch(self, swap_id: int) -> None:
        with self._lock:
            if swap_id not in self._threads:
                return
            self._stopping.add(swap_id)
            call = self._calls.get(swap_id)
        if call is not None:
            call.cancel()

    def close(self, timeout: float = 5.0) -> None:
        with self._lock:
            self._closed = True
            ids = list(self._threads)
        for swap_id in ids:
            self.unwatch(swap_id)
        with self._lock:
            threads = list(self._threads.values())
        for t in threads:
            t.join(timeout)

    def _should_stop(self, swap_id: int) -> bool:
        with self._lock:
            return self._closed or swap_id in self._stopping

    def _run(self, swap_id: int, payment_hash: bytes) -> None:
        backoff = _BACKOFF_INITIAL
        stop_wait = threading.Event()
        try:
            while not self._should_stop(swap_id):
                try:
                    call = self.lnd.subscribe_single_invoice(payment_hash)
                    with self._lock:
                        self._calls[swap_id] = call
                    if self._should_stop(swap_id):  # unwatch raced with (re)subscribe
                        call.cancel()
                        return
                    for invoice in call:
                        backoff = _BACKOFF_INITIAL
                        if invoice.state != InvoiceState.OPEN:
                            self.on_update(swap_id)
                        if invoice.state in _FINAL_FOR_WATCHER:
                            return
                    # Stream ended without a final state: resubscribe (first message = current state).
                    logger.warning("Invoice stream for swap %s ended, resubscribing in %.0fs", swap_id, backoff)
                except grpc.RpcError as e:
                    if self._should_stop(swap_id):
                        return
                    if e.code() == grpc.StatusCode.NOT_FOUND:
                        # Our own invoice vanished: let the worker look (it treats this as fatal).
                        self.on_update(swap_id)
                        return
                    logger.warning("Invoice stream for swap %s broke (%s), resubscribing in %.0fs",
                                   swap_id, e.code().name, backoff)
                except Exception:
                    logger.exception("Invoice watcher for swap %s failed, resubscribing in %.0fs", swap_id, backoff)
                stop_wait.wait(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)
        finally:
            with self._lock:
                self._threads.pop(swap_id, None)
                self._calls.pop(swap_id, None)
                self._stopping.discard(swap_id)
