from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VenueConfig:
    name: str
    spot: bool
    perp: bool
    orderbooks: bool


BINANCE = "binance"
BYBIT = "bybit"
OKX = "okx"
HYPERLIQUID = "hyperliquid"
UPBIT = "upbit"
DEXSCREENER = "dexscreener"
HYDROMANCER = "hydromancer"

SPOT = "spot"
PERP = "perp"
SWAP = "swap"

SUPPORTED_VENUES = {
    BINANCE: VenueConfig(BINANCE, spot=True, perp=True, orderbooks=True),
    BYBIT: VenueConfig(BYBIT, spot=True, perp=True, orderbooks=True),
    OKX: VenueConfig(OKX, spot=True, perp=True, orderbooks=True),
    HYPERLIQUID: VenueConfig(HYPERLIQUID, spot=False, perp=True, orderbooks=True),
    UPBIT: VenueConfig(UPBIT, spot=True, perp=False, orderbooks=True),
}

USD_QUOTES = {"USDT", "USDC", "USD", "FDUSD", "TUSD", "BUSD"}
COMMON_QUOTES = [
    "USDT",
    "USDC",
    "FDUSD",
    "TUSD",
    "BUSD",
    "USD",
    "BTC",
    "ETH",
    "BNB",
    "KRW",
    "TRY",
    "EUR",
]

