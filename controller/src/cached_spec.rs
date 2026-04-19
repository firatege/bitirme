//! Assemble a CachedSpec from Postgres for the warm-path dispatch.
//!
//! Joins sku_runs + sku_run_models + sku_run_exog_selection + sku_run_val_residuals
//! for the most recent `completed` run of a given SKU. Returns `None` when no prior
//! completed run exists — caller falls back to /forecast/cold.

use anyhow::{Context, Result};
use serde_json::Value;
use sqlx::{PgPool, Row};

use crate::types::{CachedExogSelection, CachedModelRef, CachedSpec, CachedValResidual};

pub async fn load_latest(pool: &PgPool, sku: &str) -> Result<Option<CachedSpec>> {
    let row = sqlx::query(
        r#"
        SELECT run_id, winning_horizon::text AS h, winning_exog, winning_y_variant::text AS v,
               winning_phase::text AS ph, winning_w_rf, winning_w_xgb
        FROM sku_runs
        WHERE sku = $1 AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST, run_id DESC
        LIMIT 1
        "#,
    )
    .bind(sku)
    .fetch_optional(pool)
    .await
    .context("select latest sku_runs")?;

    let Some(row) = row else { return Ok(None) };
    let run_id: i64 = row.try_get("run_id")?;
    let winning_horizon: Option<String> = row.try_get("h")?;
    let winning_exog: Option<String> = row.try_get("winning_exog")?;
    let winning_y_variant: Option<String> = row.try_get("v")?;
    let winning_phase: Option<String> = row.try_get("ph")?;
    let winning_w_rf: Option<f64> = row.try_get("winning_w_rf")?;
    let winning_w_xgb: Option<f64> = row.try_get("winning_w_xgb")?;

    // Incomplete prior run — treat as no cache.
    let (Some(horizon), Some(exog), Some(variant), Some(phase)) =
        (winning_horizon, winning_exog, winning_y_variant, winning_phase)
    else {
        return Ok(None);
    };

    let model_rows = sqlx::query(
        r#"
        SELECT model_slot::text AS slot, column_target::text AS ct, hyperparams, blob_uri
        FROM sku_run_models WHERE run_id = $1 AND sku = $2
        "#,
    )
    .bind(run_id)
    .bind(sku)
    .fetch_all(pool)
    .await
    .context("select sku_run_models")?;

    let mut models = Vec::with_capacity(model_rows.len());
    for r in model_rows {
        let slot: String = r.try_get("slot")?;
        let ct: String = r.try_get("ct")?;
        let hp: Value = r.try_get("hyperparams")?;
        let uri: String = r.try_get("blob_uri")?;
        models.push(CachedModelRef {
            model_slot: slot,
            column_target: ct,
            hyperparams: hp,
            blob_uri: uri,
        });
    }

    let sel_rows = sqlx::query(
        r#"
        SELECT column_target::text AS ct, chosen_method, val_mae
        FROM sku_run_exog_selection WHERE run_id = $1 AND sku = $2
        "#,
    )
    .bind(run_id)
    .bind(sku)
    .fetch_all(pool)
    .await
    .context("select sku_run_exog_selection")?;

    let mut exog_selection = Vec::with_capacity(sel_rows.len());
    for r in sel_rows {
        exog_selection.push(CachedExogSelection {
            column_target: r.try_get::<String, _>("ct")?,
            chosen_method: r.try_get::<String, _>("chosen_method")?,
            val_mae: r.try_get::<Option<f64>, _>("val_mae")?.unwrap_or(0.0),
        });
    }

    let res_rows = sqlx::query(
        r#"
        SELECT exog, y_variant::text AS v, residuals
        FROM sku_run_val_residuals WHERE run_id = $1 AND sku = $2
        "#,
    )
    .bind(run_id)
    .bind(sku)
    .fetch_all(pool)
    .await
    .context("select sku_run_val_residuals")?;

    let mut val_residuals = Vec::with_capacity(res_rows.len());
    for r in res_rows {
        val_residuals.push(CachedValResidual {
            exog: r.try_get::<String, _>("exog")?,
            y_variant: r.try_get::<String, _>("v")?,
            residuals: r.try_get::<Vec<f64>, _>("residuals")?,
        });
    }

    Ok(Some(CachedSpec {
        prior_run_id: run_id,
        winning_horizon: horizon,
        winning_exog: exog,
        winning_y_variant: variant,
        winning_phase: phase,
        winning_w_rf,
        winning_w_xgb,
        models,
        exog_selection,
        val_residuals,
    }))
}
