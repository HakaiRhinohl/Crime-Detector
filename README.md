# Crypto Market Structure Anomaly Scanner

Local-first crypto market-structure anomaly scanner. It monitors non-excluded assets listed on Binance, Bybit, OKX, Hyperliquid, and Upbit, stores normalized market data, builds token-specific baselines, and emits very few high-quality Telegram alerts.

## What V1 does

- Discovers venue-listed assets and maps venue symbols to canonical assets.
- Stores normalized market, orderbook-depth, DEX, feature, liquidation-cluster, alert, and dedupe state tables.
- Uses official exchange APIs directly. MCP/connectors are not runtime dependencies.
- Runs locally with Docker Compose and can later move to one VPS.
- Keeps weaker watch-level anomaly candidates in the dashboard even when Telegram is suppressed.

## Quick start

```bash
cp .env.example .env
docker compose up postgres redis -d
alembic upgrade head
docker compose up api dashboard worker_market_data worker_features worker_alerts
```

Dashboard:

- API: `http://localhost:8000`
- Frontend: `http://localhost:5173`

Telegram starts in dry-run mode by default. Set `TELEGRAM_DRY_RUN=false`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` only after local smoke tests look clean.

## Important boundaries

V1 does not trade, predict direction, use Arkham, track wallets, discover DEX-only tokens, or alert on realized liquidations. Hydromancer is used only for pending Hyperliquid liquidation clusters.

