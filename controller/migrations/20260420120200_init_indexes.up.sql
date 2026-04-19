-- Warm-run lookup: latest completed run per SKU.
CREATE INDEX idx_sku_runs_sku_completed
    ON sku_runs (sku, completed_at DESC)
    WHERE status = 'completed';

-- Fast lookup of a specific model blob for cache reconstruction.
CREATE INDEX idx_sku_run_models_sku_slot_run
    ON sku_run_models (sku, model_slot, run_id);

-- Job queue scan — filter out completed/failed rows at query time.
CREATE INDEX idx_forecast_jobs_status
    ON forecast_jobs (status)
    WHERE status IN ('queued','claimed');

-- Panel-slice read: one SKU, ordered by ds.
CREATE INDEX idx_sales_panel_sku_ds ON sales_panel (sku, ds);
