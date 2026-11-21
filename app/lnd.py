import base64
import os
import httpx
from typing import Optional, Dict, Any
from app.config import settings

class LndClient:
    def __init__(
        self,
        host: Optional[str] = None,
        macaroon_path: Optional[str] = None,
        tls_cert_path: Optional[str] = None,
    ):
        self.host = host or settings.LND_REST_HOST
        self.macaroon_path = macaroon_path or settings.LND_MACAROON_PATH
        self.tls_cert_path = tls_cert_path or settings.LND_TLS_CERT_PATH
        self.base_url = f"https://{self.host}"
        self._macaroon_hex: Optional[str] = None

    def _get_headers(self) -> Dict[str, str]:
        if not self._macaroon_hex:
            if not os.path.exists(self.macaroon_path):
                raise FileNotFoundError(f"LND macaroon not found at {self.macaroon_path}")
            with open(self.macaroon_path, "rb") as f:
                self._macaroon_hex = f.read().hex()
        return {
            "Grpc-Metadata-macaroon": self._macaroon_hex,
            "Content-Type": "application/json",
        }

    def _get_client(self) -> httpx.AsyncClient:
        # If TLS cert exists, verify using it. If not, fallback or raise.
        verify: Any = self.tls_cert_path if os.path.exists(self.tls_cert_path) else False
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._get_headers(),
            verify=verify,
            timeout=30.0,
        )

    async def get_info(self) -> dict:
        async with self._get_client() as client:
            resp = await client.get("/v1/getinfo")
            resp.raise_for_status()
            return resp.json()

    async def get_blockchain_balance(self) -> dict:
        async with self._get_client() as client:
            resp = await client.get("/v1/balance/blockchain")
            resp.raise_for_status()
            return resp.json()

    async def estimate_fee(self, target_conf: int = 2) -> dict:
        async with self._get_client() as client:
            resp = await client.get("/v1/fee-estimates", params={"target_conf": target_conf})
            if resp.status_code == 200:
                return resp.json()
            return {}

    async def add_hold_invoice(
        self,
        payment_hash_bytes: bytes,
        value_sat: int,
        memo: str = "",
        expiry_seconds: int = 3600,
    ) -> dict:
        """
        Creates a hold invoice in LND (/v2/invoices/hodl).
        payment_hash: bytes, sent as base64 string in JSON body.
        Returns: {"payment_request": "...", "add_index": "..."}
        """
        hash_b64 = base64.b64encode(payment_hash_bytes).decode("ascii")
        body = {
            "hash": hash_b64,
            "value": str(value_sat),
            "memo": memo,
            "expiry": str(expiry_seconds),
        }
        async with self._get_client() as client:
            resp = await client.post("/v2/invoices/hodl", json=body)
            resp.raise_for_status()
            return resp.json()

    async def lookup_invoice(self, payment_hash_bytes: bytes) -> dict:
        """
        Looks up invoice status (/v2/invoices/lookup).
        Hash is passed as base64 string.
        """
        hash_b64 = base64.b64encode(payment_hash_bytes).decode("ascii")
        async with self._get_client() as client:
            resp = await client.get(
                "/v2/invoices/lookup",
                params={"payment_hash": hash_b64},
            )
            resp.raise_for_status()
            return resp.json()

    async def send_coins(
        self,
        addr: str,
        amount_sat: int,
        sat_per_vbyte: Optional[int] = None,
        target_conf: Optional[int] = None,
    ) -> dict:
        """
        Sends on-chain BTC via /v1/transactions.
        Returns: {"txid": "..."}
        """
        body: Dict[str, Any] = {
            "addr": addr,
            "amount": str(amount_sat),
        }
        if sat_per_vbyte is not None and sat_per_vbyte > 0:
            body["sat_per_vbyte"] = str(sat_per_vbyte)
        elif target_conf:
            body["target_conf"] = target_conf

        async with self._get_client() as client:
            resp = await client.post("/v1/transactions", json=body)
            resp.raise_for_status()
            return resp.json()

    async def settle_invoice(self, preimage_bytes: bytes) -> dict:
        """
        Settles a hold invoice (/v2/invoices/settle).
        preimage: bytes sent as base64 string.
        """
        preimage_b64 = base64.b64encode(preimage_bytes).decode("ascii")
        body = {"preimage": preimage_b64}
        async with self._get_client() as client:
            resp = await client.post("/v2/invoices/settle", json=body)
            resp.raise_for_status()
            return resp.json()

    async def cancel_invoice(self, payment_hash_bytes: bytes) -> dict:
        """
        Cancels a hold invoice (/v2/invoices/cancel).
        payment_hash: bytes sent as base64 string.
        """
        hash_b64 = base64.b64encode(payment_hash_bytes).decode("ascii")
        body = {"payment_hash": hash_b64}
        async with self._get_client() as client:
            resp = await client.post("/v2/invoices/cancel", json=body)
            resp.raise_for_status()
            return resp.json()

lnd_client = LndClient()
