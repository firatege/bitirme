-- Bounded-cardinality fields backed by Postgres ENUM types.
-- Evolution: use `ALTER TYPE ... ADD VALUE 'new_value' AFTER 'existing'` for extensions.
-- Never DROP enum values in-place; create a new type + rewrite columns if needed.

CREATE TYPE run_status      AS ENUM ('queued','running','completed','failed');
CREATE TYPE sku_run_status  AS ENUM ('queued','running','completed','failed','cached_hit');
CREATE TYPE sku_run_mode    AS ENUM ('cold','warm','warm_with_refit');
CREATE TYPE horizon_kind    AS ENUM ('Full','Short3');
CREATE TYPE phase_kind      AS ENUM ('PRE','REFIT');
CREATE TYPE y_variant_kind  AS ENUM ('RF','XGB','Y-ENS','TSB','Croston','SBA');
CREATE TYPE column_target   AS ENUM ('y','orders','stock');
CREATE TYPE exog_column     AS ENUM ('orders','stock');
CREATE TYPE model_slot      AS ENUM (
    'rf_y_pre','xgb_y_pre','rf_y_refit','xgb_y_refit',
    'ml_exog_rf_orders','ml_exog_rf_stock',
    'ml_exog_xgb_orders','ml_exog_xgb_stock',
    'prophet_orders','prophet_stock',
    'sarima_orders','sarima_stock',
    'ets_orders','ets_stock'
);
CREATE TYPE job_status      AS ENUM ('queued','claimed','running','completed','failed');
