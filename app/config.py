from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LND
    LND_REST_HOST: str = "127.0.0.1:8081"
    LND_MACAROON_PATH: str = "/home/lucas/.polar/networks/3/volumes/lnd/Kross/data/chain/bitcoin/regtest/admin.macaroon"
    LND_TLS_CERT_PATH: str = "/home/lucas/.polar/networks/3/volumes/lnd/Kross/tls.cert"

    # Bitcoin & Swaps
    BITCOIN_NETWORK: str = "regtest"  # mainnet, testnet, regtest
    SWAP_FEE_RATE: float = 0.006     # 0.6%
    MIN_PAYOUT_SAT: int = 546        # Dust limit
    MIN_SWAP_SAT: int = 1000
    MAX_SWAP_SAT: int = 50_000_000
    MIN_SAT_PER_VBYTE: int = 1

    # LNURL & Server
    DOMAIN: str = "127.0.0.1:8000"
    EXTERNAL_URL: str = "http://127.0.0.1:8000"

    # Database
    DATABASE_URL: str = "sqlite:///./swapservice.db"

    # App
    LOG_LEVEL: str = "INFO"

settings = Settings()
