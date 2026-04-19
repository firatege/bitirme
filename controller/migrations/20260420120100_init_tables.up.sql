-- Source-of-truth panel + per-SKU policy. Seeded from CSVs by `controller seed`.
CREATE TABLE sales_panel (
    sku     TEXT NOT NULL,
    ds      DATE NOT NULL,
    y       DOUBLE PRECISION,
    orders  DOUBLE PRECISION,
    stock   DOUBLE PRECISION,
    PRIMARY KEY (sku, ds)
);

CREATE TABLE sku_config (
    sku                     TEXT PRIMARY KEY,
    t_check                 INT NOT NULL,
    h_cover                 INT NOT NULL,
    q_target                DOUBLE PRECISION NOT NULL,
    lead_time_mo            INT NOT NULL DEFAULT 0,
    moq                     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    lot_size                DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    starting_stock_override DOUBLE PRECISION
);

-- Run + per-SKU-per-run tables.
CREATE TABLE forecast_runs (
    run_id            BIGSERIAL PRIMARY KEY,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    pipeline_version  TEXT NOT NULL,
    data_version_hash TEXT NOT NULL,
    config_json       JSONB NOT NULL,
    status            run_status NOT NULL
);

CREATE TABLE sku_runs (
    run_id            BIGINT NOT NULL REFERENCES forecast_runs(run_id),
    sku               TEXT NOT NULL,
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    status            sku_run_status NOT NULL,
    mode              sku_run_mode NOT NULL,
    winning_horizon   horizon_kind,
    winning_exog      TEXT,
    winning_y_variant y_variant_kind,
    winning_phase     phase_kind,
    winning_mae       DOUBLE PRECISION,
    winning_rmse      DOUBLE PRECISION,
    winning_w_rf      DOUBLE PRECISION,
    winning_w_xgb     DOUBLE PRECISION,
    p_stockout_3m     DOUBLE PRECISION,
    p_stockout_6m     DOUBLE PRECISION,
    e_t_stockout_mo   DOUBLE PRECISION,
    PRIMARY KEY (run_id, sku)
);

CREATE TABLE sku_run_combinations (
    run_id          BIGINT NOT NULL,
    sku             TEXT NOT NULL,
    horizon         horizon_kind NOT NULL,
    exog            TEXT NOT NULL,
    y_variant       y_variant_kind NOT NULL,
    phase           phase_kind NOT NULL,
    mae             DOUBLE PRECISION,
    rmse            DOUBLE PRECISION,
    mape            DOUBLE PRECISION,
    w_rf            DOUBLE PRECISION,
    w_xgb           DOUBLE PRECISION,
    p_stockout_3m   DOUBLE PRECISION,
    p_stockout_6m   DOUBLE PRECISION,
    e_t_stockout_mo DOUBLE PRECISION,
    PRIMARY KEY (run_id, sku, horizon, exog, y_variant, phase)
);

CREATE TABLE sku_run_models (
    run_id        BIGINT NOT NULL,
    sku           TEXT NOT NULL,
    model_slot    model_slot NOT NULL,
    column_target column_target NOT NULL,
    hyperparams   JSONB NOT NULL,
    blob_uri      TEXT NOT NULL,
    fit_seconds   DOUBLE PRECISION,
    PRIMARY KEY (run_id, sku, model_slot)
);

CREATE TABLE sku_run_exog_selection (
    run_id        BIGINT NOT NULL,
    sku           TEXT NOT NULL,
    column_target exog_column NOT NULL,
    chosen_method TEXT NOT NULL,
    val_mae       DOUBLE PRECISION,
    PRIMARY KEY (run_id, sku, column_target)
);

CREATE TABLE sku_run_val_residuals (
    run_id     BIGINT NOT NULL,
    sku        TEXT NOT NULL,
    exog       TEXT NOT NULL,
    y_variant  y_variant_kind NOT NULL,
    residuals  DOUBLE PRECISION[] NOT NULL,
    PRIMARY KEY (run_id, sku, exog, y_variant)
);

CREATE TABLE sku_run_recommendation (
    run_id            BIGINT NOT NULL,
    sku               TEXT NOT NULL,
    starting_stock    DOUBLE PRECISION,
    t_check           INT,
    h_cover           INT,
    q_target          DOUBLE PRECISION,
    moq               DOUBLE PRECISION,
    lot_size          DOUBLE PRECISION,
    cum_demand_q      DOUBLE PRECISION,
    order_qty_raw     DOUBLE PRECISION,
    order_qty_rounded DOUBLE PRECISION,
    PRIMARY KEY (run_id, sku)
);

CREATE TABLE forecast_jobs (
    job_id     BIGSERIAL PRIMARY KEY,
    run_id     BIGINT NOT NULL REFERENCES forecast_runs(run_id),
    sku        TEXT NOT NULL,
    status     job_status NOT NULL,
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ,
    attempts   INT NOT NULL DEFAULT 0,
    last_error TEXT,
    UNIQUE (run_id, sku)
);
