#!/usr/bin/env bash
# One-shot seed: ingest the canonical panel + per-SKU config CSVs into Postgres.
#
# Preconditions:
#   - `docker compose up -d` has run and the `postgres`/`controller` services are healthy.
#   - panel_sales_orders_stock.csv + sku_config.csv live at the repo root (baked into the
#     controller image during build, so they're already at /app/ inside the container).
#
# Idempotent: re-running only upserts — safe if some rows already exist.
set -euo pipefail

PANEL="${PANEL:-/app/panel_sales_orders_stock.csv}"
CONFIG="${CONFIG:-/app/sku_config.csv}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

echo ">> waiting for controller REST API on :9000..."
until curl -fsS http://localhost:9000/healthz >/dev/null 2>&1; do
    sleep 2
done
echo ">> controller is live"

echo ">> running migrations (no-op if already applied)..."
docker compose -f "$COMPOSE_FILE" exec -T controller controller migrate

echo ">> seeding panel ($PANEL) + config ($CONFIG)..."
docker compose -f "$COMPOSE_FILE" exec -T controller \
    controller seed --panel "$PANEL" --config "$CONFIG"

echo ">> verifying row counts..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U bitirme -d bitirme -c "
        SELECT
            (SELECT COUNT(*) FROM sales_panel)  AS panel_rows,
            (SELECT COUNT(*) FROM sku_config)   AS config_rows,
            (SELECT COUNT(DISTINCT sku) FROM sales_panel) AS distinct_skus;"

echo ">> seed complete"
