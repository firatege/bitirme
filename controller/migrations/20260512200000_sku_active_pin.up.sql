-- Per-SKU pin to a specific historical run. When set, all dashboard reads
-- (latest detail, predictions) AND the warm-path cached spec query honor this
-- pin instead of "most recently completed". Used for soft rollback when a new
-- model produces a surprising recommendation and the operator wants to revert
-- to last month's behaviour without re-running anything.
CREATE TABLE sku_active_pin (
    sku             TEXT PRIMARY KEY,
    pinned_run_id   BIGINT NOT NULL REFERENCES forecast_runs(run_id),
    pinned_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pinned_by       TEXT
);
