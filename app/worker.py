import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Swap, SwapStatus
from app.lnd import lnd_client
from app.swaps import get_fee_rate_sat_per_vbyte

logger = logging.getLogger("ln2oc.worker")

class SwapWorker:
    def __init__(self, poll_interval_seconds: float = 1.0, session_factory=None):
        self.poll_interval = poll_interval_seconds
        self.session_factory = session_factory or SessionLocal
        self._running = False
        self._task: asyncio.Task | None = None

    def _get_db(self) -> Session:
        return self.session_factory()

    async def start(self):
        self._running = True
        logger.info("Starting SwapWorker...")
        # Step 1: Recover unfinished swaps from previous crash/restart
        await self.recover_swaps()
        # Step 2: Start background loop
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SwapWorker stopped.")

    async def recover_swaps(self):
        """
        Recovers swaps across application restarts:
        - If BROADCASTED but not SETTLED: settle the hold invoice! (tx was already sent)
        - If ACCEPTED: check LND invoice state. If still ACCEPTED, proceed to broadcast & settle.
        - If PENDING: check if invoice was accepted while offline, or expired/canceled.
        """
        logger.info("Running swap recovery check...")
        db: Session = self._get_db()
        try:
            # 1. Any swap that has status BROADCASTED must be settled immediately
            broadcasted_swaps = db.execute(
                select(Swap).where(Swap.status == SwapStatus.BROADCASTED)
            ).scalars().all()
            for swap in broadcasted_swaps:
                logger.info("Recovering BROADCASTED swap %s (txid: %s)", swap.id, swap.txid)
                await self._settle_swap(db, swap)

            # 2. Any ACCEPTED or PENDING swap
            active_swaps = db.execute(
                select(Swap).where(Swap.status.in_([SwapStatus.PENDING, SwapStatus.ACCEPTED]))
            ).scalars().all()
            for swap in active_swaps:
                await self._process_active_swap(db, swap)
        except Exception as e:
            logger.exception("Error during swap recovery: %s", e)
        finally:
            db.close()

    async def _run_loop(self):
        while self._running:
            try:
                await self._poll_swaps()
            except Exception as e:
                logger.exception("Error in SwapWorker loop: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def _poll_swaps(self):
        db: Session = self._get_db()
        try:
            swaps = db.execute(
                select(Swap).where(
                    Swap.status.in_([SwapStatus.PENDING, SwapStatus.ACCEPTED, SwapStatus.BROADCASTED])
                )
            ).scalars().all()

            for swap in swaps:
                await self._process_active_swap(db, swap)
        finally:
            db.close()

    async def _process_active_swap(self, db: Session, swap: Swap):
        """
        Core state machine for an active swap:
        1. If BROADCASTED: txid is known, settle the invoice.
        2. If PENDING: query LND invoice status.
           - If ACCEPTED: advance to ACCEPTED status, then send BTC on-chain.
           - If CANCELED: mark FAILED.
           - If SETTLED: mark SETTLED (if already settled).
        3. If ACCEPTED:
           - Send BTC on-chain.
           - Store txid and mark BROADCASTED (committed).
           - Settle the hold invoice and mark SETTLED.
           - If on-chain send fails: cancel the hold invoice and mark FAILED.
        """
        payment_hash_bytes = bytes.fromhex(swap.payment_hash)

        # Case 1: BROADCASTED (tx sent, must settle hold invoice)
        if swap.status == SwapStatus.BROADCASTED:
            await self._settle_swap(db, swap)
            return

        # Query LND for invoice state
        try:
            inv_info = await lnd_client.lookup_invoice(payment_hash_bytes)
        except Exception as e:
            logger.warning("Failed to lookup invoice %s: %s", swap.payment_hash, e)
            return

        state = inv_info.get("state")
        logger.debug("Swap %s invoice state: %s", swap.id, state)

        if state == "ACCEPTED":
            # Payment arrived and is being held by LND!
            if swap.status == SwapStatus.PENDING:
                swap.status = SwapStatus.ACCEPTED
                db.commit()
                logger.info("Swap %s transitioned to ACCEPTED", swap.id)

            # Send BTC on-chain
            await self._execute_onchain_and_settle(db, swap)

        elif state == "CANCELED":
            if swap.status != SwapStatus.FAILED:
                logger.warning("Swap %s invoice was canceled in LND", swap.id)
                swap.status = SwapStatus.FAILED
                db.commit()

        elif state == "SETTLED":
            if swap.status != SwapStatus.SETTLED:
                logger.info("Swap %s invoice is already SETTLED in LND", swap.id)
                swap.status = SwapStatus.SETTLED
                db.commit()

    async def _execute_onchain_and_settle(self, db: Session, swap: Swap):
        """
        Reliability guarantees:
        1. Never send the same swap twice: check if txid already exists.
        2. Send BTC on-chain.
        3. Persist txid and status BROADCASTED immediately.
        4. Settle Hold Invoice.
        5. If send fails: cancel Hold Invoice and mark FAILED.
        """
        # Guard: If swap already has txid, DO NOT re-broadcast!
        if swap.txid:
            logger.info("Swap %s already has txid %s, skipping broadcast and settling", swap.id, swap.txid)
            swap.status = SwapStatus.BROADCASTED
            db.commit()
            await self._settle_swap(db, swap)
            return

        sat_per_vbyte = await get_fee_rate_sat_per_vbyte()
        payment_hash_bytes = bytes.fromhex(swap.payment_hash)

        logger.info(
            "Broadcasting on-chain transaction for swap %s: %d sats to %s (fee_rate %d sat/vB)...",
            swap.id, swap.payout_sat, swap.btc_address, sat_per_vbyte
        )

        try:
            send_res = await lnd_client.send_coins(
                addr=swap.btc_address,
                amount_sat=swap.payout_sat,
                sat_per_vbyte=sat_per_vbyte,
            )
            txid = send_res.get("txid")
            if not txid:
                raise RuntimeError(f"LND send_coins did not return txid: {send_res}")

            logger.info("Swap %s on-chain transaction broadcasted! txid: %s", swap.id, txid)

            # Persist TXID and status BROADCASTED BEFORE settling invoice!
            swap.txid = txid
            swap.status = SwapStatus.BROADCASTED
            db.commit()

        except Exception as e:
            logger.exception("Failed to send on-chain transaction for swap %s: %s", swap.id, e)
            # Cancel the Hold Invoice so the sender gets their funds back!
            try:
                logger.info("Canceling hold invoice for failed swap %s", swap.id)
                await lnd_client.cancel_invoice(payment_hash_bytes)
            except Exception as ce:
                logger.error("Failed to cancel hold invoice %s: %s", swap.payment_hash, ce)

            swap.status = SwapStatus.FAILED
            db.commit()
            return

        # Now settle the hold invoice
        await self._settle_swap(db, swap)

    async def _settle_swap(self, db: Session, swap: Swap):
        """
        Settles the hold invoice using the stored preimage.
        """
        if not swap.preimage:
            logger.error("Swap %s is missing preimage! Cannot settle.", swap.id)
            return

        preimage_bytes = bytes.fromhex(swap.preimage)
        try:
            logger.info("Settling hold invoice for swap %s (txid: %s)...", swap.id, swap.txid)
            await lnd_client.settle_invoice(preimage_bytes)
            swap.status = SwapStatus.SETTLED
            db.commit()
            logger.info("Swap %s successfully SETTLED! Payout: %d sats, txid: %s", swap.id, swap.payout_sat, swap.txid)
        except Exception as e:
            logger.error("Failed to settle hold invoice for swap %s: %s", swap.id, e)
            # If it failed to settle (e.g. network hiccup), it remains BROADCASTED and will retry on next poll

swap_worker = SwapWorker()
