from __future__ import annotations

from decimal import Decimal

from app.universe.symbol_mapper import normalize_symbol


def test_binance_multiplier_symbol() -> None:
    mapping = normalize_symbol("binance", "1000PEPEUSDT", "perp")
    assert mapping.canonical_symbol == "PEPE"
    assert mapping.quote_asset == "USDT"
    assert mapping.contract_multiplier == Decimal("1000")


def test_okx_swap_symbol() -> None:
    mapping = normalize_symbol("okx", "WIF-USDT-SWAP", "perp")
    assert mapping.canonical_symbol == "WIF"
    assert mapping.quote_asset == "USDT"


def test_upbit_krw_symbol() -> None:
    mapping = normalize_symbol("upbit", "KRW-WIF", "spot")
    assert mapping.canonical_symbol == "WIF"
    assert mapping.quote_asset == "KRW"


def test_override_wins() -> None:
    mapping = normalize_symbol(
        "hyperliquid",
        "kPEPE",
        "perp",
        overrides={("hyperliquid", "kPEPE"): ("PEPE", Decimal("1000"))},
    )
    assert mapping.canonical_symbol == "PEPE"
    assert mapping.contract_multiplier == Decimal("1000")

