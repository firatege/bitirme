//! Dispatch a single SKU to the Python worker and persist the result.

use anyhow::{Context, Result};
use serde_json::Value;
use sqlx::{PgPool, Row};
use std::path::PathBuf;
use time::Date;
use tracing::info;

use crate::api::WorkerClient;
use crate::cached_spec;
use crate::types::{ForecastColdRequest, ForecastResult, ForecastWarmRequest, ParamsRow};

pub struct Orchestrator<'a> {
    pub pool: &'a PgPool,
    pub worker: &'a WorkerClient,
    pub model_dir: PathBuf,
    pub pipeline_version: String,
}

impl<'a> Orchestrator<'a> {
    /// CLI entrypoint — creates a fresh `forecast_runs` row, then dispatches cold.
    pub async fn run_single_sku_cold(&self, sku: &str) -> Result<i64> {
        let run_id = self.create_run(sku).await?;
        self.dispatch_cold(run_id, sku).await?;
        self.complete_run(run_id).await?;
        Ok(run_id)
    }

    /// CLI entrypoint — creates a fresh `forecast_runs` row, picks warm-or-cold.
    pub async fn run_single_sku(&self, sku: &str, check_drift: bool) -> Result<i64> {
        let run_id = self.create_run(sku).await?;
        self.dispatch(run_id, sku, check_drift).await?;
        self.complete_run(run_id).await?;
        Ok(run_id)
    }

    /// Queue entrypoint — the claim loop already has a `run_id` from the API/monthly-run
    /// enqueue step; we do NOT create another forecast_runs row. Used when the caller
    /// already owns the run lifecycle.
    pub async fn dispatch_for_run(&self, run_id: i64, sku: &str, check_drift: bool) -> Result<()> {
        self.dispatch(run_id, sku, check_drift).await
    }

    async fn dispatch(&self, run_id: i64, sku: &str, check_drift: bool) -> Result<()> {
        let cached = cached_spec::load_latest(self.pool, sku).await?;
        let Some(spec) = cached else {
            info!(sku, "no prior run; falling through to cold");
            return self.dispatch_cold(run_id, sku).await;
        };

        let panel_rows = self.load_panel_rows(sku).await?;
        if panel_rows.is_empty() {
            anyhow::bail!("no rows in sales_panel for sku {sku}");
        }
        let params = self.load_params(sku).await?;
        let blob_dir = self.model_dir.join(sku).join(run_id.to_string());

        if check_drift {
            match self.worker.drift_check(sku, &panel_rows, &params, &spec).await {
                Ok(d) if d.drift_triggered => {
                    info!(sku, new_mae = d.new_mae, cached_mae = d.cached_mae, "drift detected → cold");
                    return self.fall_through_cold(sku, run_id, panel_rows, params, blob_dir).await;
                }
                Ok(d) => info!(sku, new_mae = d.new_mae, cached_mae = d.cached_mae, "no drift"),
                Err(e) => tracing::warn!(sku, error = %e, "drift check failed; proceeding warm"),
            }
        }

        let warm_req = ForecastWarmRequest {
            sku: sku.to_string(),
            run_id,
            panel_rows,
            params_row: params,
            blob_dir: blob_dir.to_string_lossy().into_owned(),
            cached_spec: spec,
        };
        info!(sku, run_id, "dispatching /forecast/warm");
        let result = self.worker.forecast_warm(&warm_req).await?;
        self.persist_result(&result).await?;
        Ok(())
    }

    async fn dispatch_cold(&self, run_id: i64, sku: &str) -> Result<()> {
        let panel_rows = self.load_panel_rows(sku).await?;
        if panel_rows.is_empty() {
            anyhow::bail!("no rows in sales_panel for sku {sku}");
        }
        let params = self.load_params(sku).await?;
        let blob_dir = self.model_dir.join(sku).join(run_id.to_string());
        let req = ForecastColdRequest {
            sku: sku.to_string(),
            run_id,
            panel_rows,
            params_row: params,
            blob_dir: blob_dir.to_string_lossy().into_owned(),
        };
        info!(sku, run_id, "dispatching /forecast/cold");
        let result = self.worker.forecast_cold(&req).await?;
        self.persist_result(&result).await?;
        Ok(())
    }

    async fn fall_through_cold(
        &self,
        sku: &str,
        run_id: i64,
        panel_rows: Vec<Value>,
        params: ParamsRow,
        blob_dir: std::path::PathBuf,
    ) -> Result<()> {
        let req = ForecastColdRequest {
            sku: sku.to_string(),
            run_id,
            panel_rows,
            params_row: params,
            blob_dir: blob_dir.to_string_lossy().into_owned(),
        };
        info!(sku, run_id, "dispatching /forecast/cold (post-drift fallback)");
        let result = self.worker.forecast_cold(&req).await?;
        self.persist_result(&result).await?;
        Ok(())
    }

    async fn create_run(&self, seeding_sku: &str) -> Result<i64> {
        let config_json = serde_json::json!({ "single_sku": seeding_sku });
        let data_version_hash = self.hash_panel().await.unwrap_or_else(|_| "unknown".to_string());
        let row = sqlx::query(
            r#"
            INSERT INTO forecast_runs (pipeline_version, data_version_hash, config_json, status)
            VALUES ($1, $2, $3, 'running'::run_status)
            RETURNING run_id
            "#,
        )
        .bind(&self.pipeline_version)
        .bind(&data_version_hash)
        .bind(config_json)
        .fetch_one(self.pool)
        .await
        .context("INSERT forecast_runs")?;
        let run_id: i64 = row.try_get("run_id")?;
        Ok(run_id)
    }

    async fn complete_run(&self, run_id: i64) -> Result<()> {
        sqlx::query(
            "UPDATE forecast_runs SET completed_at = NOW(), status = 'completed' WHERE run_id = $1",
        )
        .bind(run_id)
        .execute(self.pool)
        .await?;
        Ok(())
    }

    async fn hash_panel(&self) -> Result<String> {
        let row = sqlx::query(
            "SELECT md5(string_agg(sku || '|' || ds::text || '|' || COALESCE(y::text,'') || '|' || \
             COALESCE(orders::text,'') || '|' || COALESCE(stock::text,''), ',' ORDER BY sku, ds)) AS h \
             FROM sales_panel",
        )
        .fetch_one(self.pool)
        .await?;
        let h: Option<String> = row.try_get("h")?;
        Ok(h.unwrap_or_default())
    }

    async fn load_panel_rows(&self, sku: &str) -> Result<Vec<Value>> {
        let rows = sqlx::query(
            "SELECT ds, y, orders, stock FROM sales_panel WHERE sku = $1 ORDER BY ds",
        )
        .bind(sku)
        .fetch_all(self.pool)
        .await?;
        let mut out = Vec::with_capacity(rows.len());
        for r in rows {
            let ds: Date = r.try_get("ds")?;
            let y: Option<f64> = r.try_get("y")?;
            let orders: Option<f64> = r.try_get("orders")?;
            let stock: Option<f64> = r.try_get("stock")?;
            let ds_str = ds
                .format(&time::format_description::well_known::Iso8601::DATE)
                .context("format ds")?;
            out.push(serde_json::json!({
                "ds": ds_str,
                "y": y.unwrap_or(0.0),
                "orders": orders.unwrap_or(0.0),
                "stock": stock.unwrap_or(0.0),
            }));
        }
        Ok(out)
    }

    async fn load_params(&self, sku: &str) -> Result<ParamsRow> {
        let r = sqlx::query(
            "SELECT t_check, h_cover, q_target, lead_time_mo, moq, lot_size, starting_stock_override \
             FROM sku_config WHERE sku = $1",
        )
        .bind(sku)
        .fetch_optional(self.pool)
        .await?;
        let r = r.with_context(|| format!("sku_config missing for {sku}"))?;
        Ok(ParamsRow {
            t_check: r.try_get("t_check")?,
            h_cover: r.try_get("h_cover")?,
            q_target: r.try_get("q_target")?,
            lead_time_mo: r.try_get("lead_time_mo")?,
            moq: r.try_get("moq")?,
            lot_size: r.try_get("lot_size")?,
            starting_stock_override: r.try_get("starting_stock_override")?,
        })
    }

    /// Single transaction: insert sku_runs + combinations + models + exog_selection +
    /// val_residuals + recommendation. Called after a successful /forecast/cold response.
    pub async fn persist_result(&self, result: &ForecastResult) -> Result<()> {
        let mut tx = self.pool.begin().await?;

        // sku_runs row with the winning combo summary
        sqlx::query(
            r#"
            INSERT INTO sku_runs (
                run_id, sku, started_at, completed_at, status, mode,
                winning_horizon, winning_exog, winning_y_variant, winning_phase,
                winning_mae, winning_rmse, winning_w_rf, winning_w_xgb,
                p_stockout_3m, p_stockout_6m, e_t_stockout_mo
            ) VALUES (
                $1, $2, NOW(), NOW(), 'completed'::sku_run_status, $3::sku_run_mode,
                $4::horizon_kind, $5, $6::y_variant_kind, $7::phase_kind,
                $8, $9, $10, $11, $12, $13, $14
            )
            ON CONFLICT (run_id, sku) DO UPDATE SET
                completed_at = EXCLUDED.completed_at,
                status = EXCLUDED.status,
                mode = EXCLUDED.mode,
                winning_horizon = EXCLUDED.winning_horizon,
                winning_exog = EXCLUDED.winning_exog,
                winning_y_variant = EXCLUDED.winning_y_variant,
                winning_phase = EXCLUDED.winning_phase,
                winning_mae = EXCLUDED.winning_mae,
                winning_rmse = EXCLUDED.winning_rmse,
                winning_w_rf = EXCLUDED.winning_w_rf,
                winning_w_xgb = EXCLUDED.winning_w_xgb,
                p_stockout_3m = EXCLUDED.p_stockout_3m,
                p_stockout_6m = EXCLUDED.p_stockout_6m,
                e_t_stockout_mo = EXCLUDED.e_t_stockout_mo
            "#,
        )
        .bind(result.run_id)
        .bind(&result.sku)
        .bind(&result.mode)
        .bind(&result.winning.horizon)
        .bind(&result.winning.exog)
        .bind(&result.winning.y_variant)
        .bind(&result.winning.phase)
        .bind(result.winning.mae)
        .bind(result.winning.rmse)
        .bind(result.winning.w_rf)
        .bind(result.winning.w_xgb)
        .bind(result.winning.p_stockout_3m)
        .bind(result.winning.p_stockout_6m)
        .bind(result.winning.e_t_stockout_mo)
        .execute(&mut *tx)
        .await
        .context("insert sku_runs")?;

        // Combinations — bulk via UNNEST
        if !result.combinations.is_empty() {
            let mut horizons = Vec::with_capacity(result.combinations.len());
            let mut exogs = Vec::with_capacity(result.combinations.len());
            let mut variants = Vec::with_capacity(result.combinations.len());
            let mut phases = Vec::with_capacity(result.combinations.len());
            let mut maes = Vec::with_capacity(result.combinations.len());
            let mut rmses = Vec::with_capacity(result.combinations.len());
            let mut mapes = Vec::with_capacity(result.combinations.len());
            let mut wrfs = Vec::with_capacity(result.combinations.len());
            let mut wxgbs = Vec::with_capacity(result.combinations.len());
            let mut p3s = Vec::with_capacity(result.combinations.len());
            let mut p6s = Vec::with_capacity(result.combinations.len());
            let mut ets = Vec::with_capacity(result.combinations.len());
            for c in &result.combinations {
                horizons.push(c.horizon.clone());
                exogs.push(c.exog.clone());
                variants.push(c.y_variant.clone());
                phases.push(c.phase.clone());
                maes.push(c.mae);
                rmses.push(c.rmse);
                mapes.push(c.mape);
                wrfs.push(c.w_rf);
                wxgbs.push(c.w_xgb);
                p3s.push(c.p_stockout_3m);
                p6s.push(c.p_stockout_6m);
                ets.push(c.e_t_stockout_mo);
            }
            sqlx::query(
                r#"
                INSERT INTO sku_run_combinations (
                    run_id, sku, horizon, exog, y_variant, phase,
                    mae, rmse, mape, w_rf, w_xgb, p_stockout_3m, p_stockout_6m, e_t_stockout_mo
                )
                SELECT $1, $2, h::horizon_kind, e, v::y_variant_kind, ph::phase_kind,
                       mae, rmse, mape, wrf, wxgb, p3, p6, etm
                FROM UNNEST(
                    $3::text[], $4::text[], $5::text[], $6::text[],
                    $7::float8[], $8::float8[], $9::float8[],
                    $10::float8[], $11::float8[],
                    $12::float8[], $13::float8[], $14::float8[]
                ) AS t(h, e, v, ph, mae, rmse, mape, wrf, wxgb, p3, p6, etm)
                ON CONFLICT (run_id, sku, horizon, exog, y_variant, phase) DO NOTHING
                "#,
            )
            .bind(result.run_id)
            .bind(&result.sku)
            .bind(&horizons)
            .bind(&exogs)
            .bind(&variants)
            .bind(&phases)
            .bind(&maes)
            .bind(&rmses)
            .bind(&mapes)
            .bind(&wrfs)
            .bind(&wxgbs)
            .bind(&p3s)
            .bind(&p6s)
            .bind(&ets)
            .execute(&mut *tx)
            .await
            .context("insert sku_run_combinations")?;
        }

        // Models
        for m in &result.models {
            sqlx::query(
                r#"
                INSERT INTO sku_run_models (run_id, sku, model_slot, column_target, hyperparams, blob_uri, fit_seconds)
                VALUES ($1, $2, $3::model_slot, $4::column_target, $5, $6, $7)
                ON CONFLICT (run_id, sku, model_slot) DO UPDATE SET
                    column_target = EXCLUDED.column_target,
                    hyperparams = EXCLUDED.hyperparams,
                    blob_uri = EXCLUDED.blob_uri,
                    fit_seconds = EXCLUDED.fit_seconds
                "#,
            )
            .bind(result.run_id)
            .bind(&result.sku)
            .bind(&m.model_slot)
            .bind(&m.column_target)
            .bind(&m.hyperparams)
            .bind(&m.blob_uri)
            .bind(m.fit_seconds)
            .execute(&mut *tx)
            .await
            .context("insert sku_run_models")?;
        }

        // Exog selection per column
        for s in &result.exog_selection {
            sqlx::query(
                r#"
                INSERT INTO sku_run_exog_selection (run_id, sku, column_target, chosen_method, val_mae)
                VALUES ($1, $2, $3::exog_column, $4, $5)
                ON CONFLICT (run_id, sku, column_target) DO UPDATE SET
                    chosen_method = EXCLUDED.chosen_method,
                    val_mae = EXCLUDED.val_mae
                "#,
            )
            .bind(result.run_id)
            .bind(&result.sku)
            .bind(&s.column_target)
            .bind(&s.chosen_method)
            .bind(s.val_mae)
            .execute(&mut *tx)
            .await
            .context("insert sku_run_exog_selection")?;
        }

        // VAL residuals
        for r in &result.val_residuals {
            sqlx::query(
                r#"
                INSERT INTO sku_run_val_residuals (run_id, sku, exog, y_variant, residuals)
                VALUES ($1, $2, $3, $4::y_variant_kind, $5)
                ON CONFLICT (run_id, sku, exog, y_variant) DO UPDATE SET
                    residuals = EXCLUDED.residuals
                "#,
            )
            .bind(result.run_id)
            .bind(&result.sku)
            .bind(&r.exog)
            .bind(&r.y_variant)
            .bind(&r.residuals)
            .execute(&mut *tx)
            .await
            .context("insert sku_run_val_residuals")?;
        }

        // Recommendation
        let rec = &result.recommendation;
        sqlx::query(
            r#"
            INSERT INTO sku_run_recommendation (
                run_id, sku, starting_stock, t_check, h_cover, q_target,
                moq, lot_size, cum_demand_q, order_qty_raw, order_qty_rounded
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (run_id, sku) DO UPDATE SET
                starting_stock = EXCLUDED.starting_stock,
                t_check = EXCLUDED.t_check,
                h_cover = EXCLUDED.h_cover,
                q_target = EXCLUDED.q_target,
                moq = EXCLUDED.moq,
                lot_size = EXCLUDED.lot_size,
                cum_demand_q = EXCLUDED.cum_demand_q,
                order_qty_raw = EXCLUDED.order_qty_raw,
                order_qty_rounded = EXCLUDED.order_qty_rounded
            "#,
        )
        .bind(result.run_id)
        .bind(&result.sku)
        .bind(rec.starting_stock)
        .bind(rec.t_check)
        .bind(rec.h_cover)
        .bind(rec.q_target)
        .bind(rec.moq)
        .bind(rec.lot_size)
        .bind(rec.cum_demand_q)
        .bind(rec.order_qty_raw)
        .bind(rec.order_qty_rounded)
        .execute(&mut *tx)
        .await
        .context("insert sku_run_recommendation")?;

        tx.commit().await.context("commit persist_result transaction")?;
        Ok(())
    }
}
