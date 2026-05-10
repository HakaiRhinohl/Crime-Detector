from __future__ import annotations

from app.orderbooks.depth_calculator import calculate_depth


def test_depth_calculation_inside_bps() -> None:
    bids = [(99.5, 10), (99.0, 20), (97.0, 100)]
    asks = [(100.5, 10), (101.0, 20), (103.0, 100)]
    depth = calculate_depth(bids, asks)
    assert depth is not None
    assert depth.mid_price == 100
    assert depth.spread_bps == 100
    assert depth.bid_depth_50bps_usd == 995
    assert depth.ask_depth_50bps_usd == 1005
    assert depth.bid_depth_100bps_usd == 995 + 1980
    assert depth.ask_depth_100bps_usd == 1005 + 2020

