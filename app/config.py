from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


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
    BITCOIN_NETWORK: str = "regtest"  # mainnet, testnet, regtest
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
    # How long LND keeps our UTXOs leased while a payout is in flight.
    UTXO_LEASE_SECONDS: int = 86_400

    # Hold invoices
    INVOICE_EXPIRY_SECONDS: int = 3600
    # Final CLTV delta requested for the hold invoice HTLCs.
    HOLD_INVOICE_CLTV_EXPIRY: int = 144
    # Never settle an HTLC that expires in fewer blocks than this; cancel (refund) instead.
    # Must stay well above LND's own hold-invoice auto-cancel delta (~12 blocks).
    MIN_CLTV_MARGIN_BLOCKS: int = 40

    # Invoice updates arrive ONLY through SubscribeSingleInvoice (one stream per PENDING
    # swap). This interval only paces retries of our own in-flight operations
    # (fund/settle/publish/cancel) while LND is unavailable.
    WORKER_RETRY_INTERVAL_SECONDS: float = 2.0
    # Max concurrent invoice subscriptions. New swaps are refused (503) beyond this,
    # since an unwatched invoice would never be noticed.
    MAX_WATCHED_INVOICES: int = 5000

    # LNURL & Server
    DOMAIN: str = "127.0.0.1:8000"
    EXTERNAL_URL: str = "http://127.0.0.1:8000"

    # Database
    DATABASE_URL: str = "sqlite:///./ln2oc.db"
    # Exclusive lock guaranteeing a single swap worker. Defaults to "<sqlite db path>.worker.lock".
    WORKER_LOCK_FILE: str | None = None

    # App
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def _validate(self):
        errors = []
        if self.BITCOIN_NETWORK.lower() not in ("mainnet", "testnet", "regtest"):
            errors.append(f"BITCOIN_NETWORK must be mainnet/testnet/regtest, got {self.BITCOIN_NETWORK!r}")
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
        if self.MIN_CLTV_MARGIN_BLOCKS < 20:
            errors.append("MIN_CLTV_MARGIN_BLOCKS must be >= 20")
        if self.HOLD_INVOICE_CLTV_EXPIRY <= self.MIN_CLTV_MARGIN_BLOCKS + 10:
            errors.append("HOLD_INVOICE_CLTV_EXPIRY must exceed MIN_CLTV_MARGIN_BLOCKS by > 10 blocks")
        if not (0 < self.WORKER_RETRY_INTERVAL_SECONDS <= 60):
            errors.append("Require 0 < WORKER_RETRY_INTERVAL_SECONDS <= 60")
        if self.MAX_WATCHED_INVOICES < 1:
            errors.append("MAX_WATCHED_INVOICES must be >= 1")
        if self.UTXO_LEASE_SECONDS < 600:
            errors.append("UTXO_LEASE_SECONDS must be >= 600")
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
