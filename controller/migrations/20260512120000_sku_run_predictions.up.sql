-- Stores the **winning combination's** per-month prediction trajectory + bootstrap PI
-- bands for each (run_id, sku). One row per forecast month covered by the run
-- (test window for cold runs; whatever horizon the warm path produced).
--
-- Used by the dashboard to overlay forecast on the demand history chart.
-- Only winning combo is persisted — keeping it lean. Other combos' yhat lives
-- only in worker memory and the on-disk preds_*.csv files.
CREATE TABLE sku_run_predictions (
    run_id     BIGINT NOT NULL REFERENCES forecast_runs(run_id),
    sku        TEXT NOT NULL,
    ds         DATE NOT NULL,
    y          DOUBLE PRECISION,   -- ground truth at ds; NULL for future months
    yhat       DOUBLE PRECISION NOT NULL,
    pi80_lo    DOUBLE PRECISION,
    pi80_hi    DOUBLE PRECISION,
    pi95_lo    DOUBLE PRECISION,
    pi95_hi    DOUBLE PRECISION,
    PRIMARY KEY (run_id, sku, ds)
);

CREATE INDEX idx_sku_run_predictions_sku_run
    ON sku_run_predictions (sku, run_id);
