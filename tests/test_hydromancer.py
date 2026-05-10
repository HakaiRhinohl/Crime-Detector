from __future__ import annotations

from app.collectors.hydromancer_liquidations import (
    build_clusters,
    liquidation_bucket,
    parse_positions,
)


def test_parse_positions_and_clusters() -> None:
    snapshot = {
        "m": "WIF",
        "p": [
            [1.5, 1500.0, 0.0, 1000.0, 0.0, 5.0, 950.0, 10000.0],
            [2.0, 2000.0, 0.0, 1000.0, 0.0, 5.0, 951.0, 10000.0],
            [-1.0, 1200.0, 0.0, 1000.0, 0.0, 5.0, 1050.0, 10000.0],
        ],
    }
    positions = parse_positions(snapshot)
    assert len(positions) == 3
    clusters = build_clusters(snapshot)
    assert sum(cluster.positions_count for cluster in clusters) == 3
    assert {cluster.side for cluster in clusters} == {"long", "short"}


def test_liquidation_bucket_is_dynamic() -> None:
    bucket = liquidation_bucket(100.0)
    assert bucket > 0

