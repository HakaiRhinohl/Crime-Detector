from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DepthSnapshot:
    mid_price: float
    spread_bps: float
    bid_depth_50bps_usd: float
    ask_depth_50bps_usd: float
    bid_depth_100bps_usd: float
    ask_depth_100bps_usd: float
    bid_depth_200bps_usd: float
    ask_depth_200bps_usd: float
    imbalance_100bps: float | None


def _depth_usd(levels: list[tuple[float, float]], threshold: float, side: str) -> float:
    epsilon = abs(threshold) * 1e-12
    if side == "bid":
        return sum(price * size for price, size in levels if price + epsilon >= threshold)
    return sum(price * size for price, size in levels if price <= threshold + epsilon)


def calculate_depth(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> DepthSnapshot | None:
    if not bids or not asks:
        return None
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    if best_bid <= 0 or best_ask <= 0:
        return None

    mid = (best_bid + best_ask) / 2
    spread_bps = ((best_ask - best_bid) / mid) * 10_000
    bid_50 = _depth_usd(bids, mid * 0.995, "bid")
    ask_50 = _depth_usd(asks, mid * 1.005, "ask")
    bid_100 = _depth_usd(bids, mid * 0.99, "bid")
    ask_100 = _depth_usd(asks, mid * 1.01, "ask")
    bid_200 = _depth_usd(bids, mid * 0.98, "bid")
    ask_200 = _depth_usd(asks, mid * 1.02, "ask")
    denom = bid_100 + ask_100
    imbalance = (bid_100 - ask_100) / denom if denom else None
    return DepthSnapshot(
        mid_price=mid,
        spread_bps=spread_bps,
        bid_depth_50bps_usd=bid_50,
        ask_depth_50bps_usd=ask_50,
        bid_depth_100bps_usd=bid_100,
        ask_depth_100bps_usd=ask_100,
        bid_depth_200bps_usd=bid_200,
        ask_depth_200bps_usd=ask_200,
        imbalance_100bps=imbalance,
    )
