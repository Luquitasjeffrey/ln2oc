from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


APP_VERSION = "0.3.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LND
    LND_GRPC_HOST: str = "127.0.0.1:10001"
    # Override the TLS server name checked against LND's cert (e.g. when connecting via
    # host.docker.internal, which is not in the cert's SANs). Empty = use the host.
    LND_TLS_SERVER_NAME: str | None = None
    LND_MACAROON_PATH: str = "/home/lucas/.polar/networks/3/volumes/lnd/Kross/data/chain/bitcoin/regtest/admin.macaroon"
    LND_TLS_CERT_PATH: str = "/home/lucas/.polar/networks/3/volumes/lnd/Kross/tls.cert"

    # Bitcoin & Swaps
    BITCOIN_NETWORK: str = "regtest"  # mainnet, testnet (testnet3), testnet4, regtest
    SWAP_FEE_RATE: float = 0.007     # 0.7% (configurable)
    MIN_PAYOUT_SAT: int = 546        # Dust limit
    MIN_SWAP_SAT: int = 1000
    MAX_SWAP_SAT: int = 1_000_000   # aimed at small swaps (<= 1M sats)

    # On-chain fees
    MIN_SAT_PER_VBYTE: int = 1
    # Refuse to operate if LND estimates more than this (protects against absurd estimates).
    MAX_SAT_PER_VBYTE: int = 500
    # The payout pays the fee rate of the moment it is signed, but never more than this
    # many times the miner fee estimated before settling (when the payer can still be refunded).
    MINER_FEE_CAP_MULTIPLIER: float = 2.0
    FEE_TARGET_CONF: int = 2
    # Confirmations required on wallet UTXOs used to fund payouts (0 = allow unconfirmed change).
    ONCHAIN_MIN_CONFS: int = 1
    # Held payments waiting while the wallet has unconfirmed txs are paid together, in one
    # tx with one output each, once it is quiet again: at most this many per tx (1 = one
    # payout per tx). Bounded so an attacker cannot grow it.
    MAX_PAYOUT_BATCH: int = 10
    # How long LND keeps our UTXOs leased while a payout is in flight.
    UTXO_LEASE_SECONDS: int = 86_400

    # Hold invoices
    INVOICE_EXPIRY_SECONDS: int = 3600
    # Final CLTV delta requested for the hold invoice HTLCs.
    HOLD_INVOICE_CLTV_EXPIRY: int = 144
    # Never settle an HTLC that expires in fewer blocks than this; cancel (refund) instead.
    # Must stay well above LND's own hold-invoice auto-cancel delta (~12 blocks).
    MIN_CLTV_MARGIN_BLOCKS: int = 40

    # Payment detection: the worker thread looks up every PENDING invoice, one after
    # another, once per this interval (no subscriptions, no extra threads). A held HTLC
    # stays in flight for the payer meanwhile, so a long interval only delays the payout.
    INVOICE_POLL_INTERVAL_SECONDS: float = 60.0
    # Retry pace for our own in-flight operations (fund/settle/publish/cancel, or a held
    # payment waiting for the payout slot). Never re-polls every PENDING invoice.
    WORKER_RETRY_INTERVAL_SECONDS: float = 2.0
    # Max PENDING swaps (unpaid invoices). Bounds the work of each poll: new swaps are
    # refused (503) beyond this.
    MAX_PENDING_SWAPS: int = 5000

    # LNURL & Server
    DOMAIN: str = "127.0.0.1:8000"
    EXTERNAL_URL: str = "http://127.0.0.1:8000"

    # Database
    DATABASE_URL: str = "sqlite:///./ln2oc.db"
    # Exclusive lock guaranteeing a single swap worker. Defaults to "<sqlite db path>.worker.lock".
    WORKER_LOCK_FILE: str | None = None

    # Website: served by its own server, never by this service. GET / redirects here
    # (unset: GET / is a 404).
    FRONTEND_URL: str | None = None
    # Commit reported by /api/info (set at docker build). Unset: `git rev-parse HEAD`.
    GIT_COMMIT: str | None = None

    # App
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def _validate(self):
        errors = []
        if self.BITCOIN_NETWORK.lower() not in ("mainnet", "testnet", "testnet4", "regtest"):
            errors.append(f"BITCOIN_NETWORK must be mainnet/testnet/testnet4/regtest, got {self.BITCOIN_NETWORK!r}")
        if not (0 <= self.SWAP_FEE_RATE < 1):
            errors.append("SWAP_FEE_RATE must be in [0, 1)")
        if abs(self.SWAP_FEE_RATE * 10_000 - round(self.SWAP_FEE_RATE * 10_000)) > 1e-6:
            errors.append("SWAP_FEE_RATE supports at most 0.01% (basis point) precision")
        if not (0 < self.MIN_SWAP_SAT <= self.MAX_SWAP_SAT):
            errors.append("Require 0 < MIN_SWAP_SAT <= MAX_SWAP_SAT")
        if not (1.0 <= self.MINER_FEE_CAP_MULTIPLIER <= 10.0):
            errors.append("Require 1 <= MINER_FEE_CAP_MULTIPLIER <= 10")
        if not (1 <= self.MIN_SAT_PER_VBYTE <= self.MAX_SAT_PER_VBYTE):
            errors.append("Require 1 <= MIN_SAT_PER_VBYTE <= MAX_SAT_PER_VBYTE")
        if self.ONCHAIN_MIN_CONFS < 0:
            errors.append("ONCHAIN_MIN_CONFS must be >= 0")
        if self.MIN_CLTV_MARGIN_BLOCKS < 20:
            errors.append("MIN_CLTV_MARGIN_BLOCKS must be >= 20")
        if self.HOLD_INVOICE_CLTV_EXPIRY <= self.MIN_CLTV_MARGIN_BLOCKS + 10:
            errors.append("HOLD_INVOICE_CLTV_EXPIRY must exceed MIN_CLTV_MARGIN_BLOCKS by > 10 blocks")
        if not (0 < self.WORKER_RETRY_INTERVAL_SECONDS <= 60):
            errors.append("Require 0 < WORKER_RETRY_INTERVAL_SECONDS <= 60")
        if not (1 <= self.INVOICE_POLL_INTERVAL_SECONDS <= 600):
            errors.append("Require 1 <= INVOICE_POLL_INTERVAL_SECONDS <= 600")
        if self.INVOICE_EXPIRY_SECONDS <= 2 * self.INVOICE_POLL_INTERVAL_SECONDS:
            errors.append("INVOICE_EXPIRY_SECONDS must exceed 2 x INVOICE_POLL_INTERVAL_SECONDS")
        if self.MAX_PENDING_SWAPS < 1:
            errors.append("MAX_PENDING_SWAPS must be >= 1")
        if not (1 <= self.MAX_PAYOUT_BATCH <= 50):
            errors.append("Require 1 <= MAX_PAYOUT_BATCH <= 50")
        if self.UTXO_LEASE_SECONDS < 600:
            errors.append("UTXO_LEASE_SECONDS must be >= 600")
        if self.FRONTEND_URL and not self.FRONTEND_URL.startswith(("https://", "http://")):
            errors.append("FRONTEND_URL must be an http(s):// URL")
        if errors:
            raise ValueError("Invalid configuration: " + "; ".join(errors))
        return self

    def worker_lock_path(self) -> str:
        if self.WORKER_LOCK_FILE:
            return self.WORKER_LOCK_FILE
        prefix = "sqlite:///"
        if self.DATABASE_URL.startswith(prefix):
            return self.DATABASE_URL[len(prefix):] + ".worker.lock"
        raise ValueError("WORKER_LOCK_FILE must be set for non-SQLite databases")


settings = Settings()
