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
    FEE_TARGET_CONF: int = 2
    # Confirmations required on wallet UTXOs used to fund payouts (0 = allow unconfirmed change).
    ONCHAIN_MIN_CONFS: int = 1

    # Hold invoices
    INVOICE_EXPIRY_SECONDS: int = 3600
    # Final CLTV delta requested for the hold invoice HTLCs.
    HOLD_INVOICE_CLTV_EXPIRY: int = 144

    # Payment detection: the worker thread looks up every PENDING invoice, one after
    # another, once per this interval (no subscriptions, no extra threads). A held HTLC
    # stays in flight for the payer meanwhile, so a long interval only delays the payout.
    INVOICE_POLL_INTERVAL_SECONDS: float = 60.0
    # Retry pace while payments are held (waiting for the wallet to have no unconfirmed
    # tx) or LND is unavailable. Never re-polls every PENDING invoice.
    WORKER_RETRY_INTERVAL_SECONDS: float = 2.0
    # Max PENDING + INVOICE_HOLD swaps. Bounds the work of each tick and the size of a
    # payout tx (one output per held swap): new swaps are refused (503) beyond this. At
    # most 1000, so a payout tx stays well below the 100 kvB standardness limit.
    MAX_PENDING_SWAPS: int = 1000

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
        if not (1 <= self.MIN_SAT_PER_VBYTE <= self.MAX_SAT_PER_VBYTE):
            errors.append("Require 1 <= MIN_SAT_PER_VBYTE <= MAX_SAT_PER_VBYTE")
        if self.ONCHAIN_MIN_CONFS < 0:
            errors.append("ONCHAIN_MIN_CONFS must be >= 0")
        if self.HOLD_INVOICE_CLTV_EXPIRY < 40:
            errors.append("HOLD_INVOICE_CLTV_EXPIRY must be >= 40")
        if not (0 < self.WORKER_RETRY_INTERVAL_SECONDS <= 60):
            errors.append("Require 0 < WORKER_RETRY_INTERVAL_SECONDS <= 60")
        if not (1 <= self.INVOICE_POLL_INTERVAL_SECONDS <= 600):
            errors.append("Require 1 <= INVOICE_POLL_INTERVAL_SECONDS <= 600")
        if self.INVOICE_EXPIRY_SECONDS <= 2 * self.INVOICE_POLL_INTERVAL_SECONDS:
            errors.append("INVOICE_EXPIRY_SECONDS must exceed 2 x INVOICE_POLL_INTERVAL_SECONDS")
        if not (1 <= self.MAX_PENDING_SWAPS <= 1000):
            errors.append("Require 1 <= MAX_PENDING_SWAPS <= 1000")
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
