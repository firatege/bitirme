//! Controller REST API — internal HTTP interface for dashboards / callers.
//!
//! Actix-web stack (matches Stockimg-AI `services/public-api` pattern):
//!   - AppState is `Clone` + shared via `web::Data::new(state.clone())`.
//!   - Handler signature takes `web::Data<AppState>`.
//!   - Error type uses `thiserror` + `actix_web::ResponseError`.
//!
//! All trigger endpoints are async: they create forecast_runs + forecast_jobs rows and
//! spawn the claim loop in a background tokio task, returning 202 with `run_id`
//! immediately. Status is polled via GET /runs/{run_id}; forecast_jobs + sku_runs are
//! the source of truth.

use actix_cors::Cors;
use actix_web::{
    delete, get, post,
    web::{Data, Json, Path, Query},
    App, HttpResponse, HttpServer, Responder, ResponseError,
};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{PgPool, Row};
use std::net::SocketAddr;
use std::path::PathBuf;
use tracing::{error, info};

use crate::api::WorkerClient;
use crate::queue;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub worker_base_url: String,
    pub model_dir: PathBuf,
    pub pipeline_version: String,
}

pub async fn serve(addr: SocketAddr, state: AppState) -> std::io::Result<()> {
    info!(%addr, "controller REST API listening");
    HttpServer::new(move || {
        App::new()
            .app_data(Data::new(state.clone()))
            .wrap(
                Cors::default()
                    .allow_any_origin()
                    .allow_any_method()
                    .allow_any_header(),
            )
            .service(healthz)
            .service(readyz)
            .service(create_run)
            .service(list_runs)
            .service(get_run)
            .service(get_run_sku)
            .service(forecast_sku)
            .service(get_sku_latest)
            .service(get_sku_history)
            .service(get_sku_timeseries)
            .service(get_sku_predictions)
            .service(get_run_jobs)
            .service(get_sku_pin)
            .service(set_sku_pin)
            .service(delete_sku_pin)
            .service(list_skus)
    })
    .bind(addr)?
    .run()
    .await
}

// --------------------------- Health ---------------------------

#[get("/healthz")]
async fn healthz() -> impl Responder {
    HttpResponse::Ok().json(serde_json::json!({"ok": true}))
}

#[get("/readyz")]
async fn readyz(state: Data<AppState>) -> impl Responder {
    let db_ok: bool = sqlx::query_scalar::<_, i32>("SELECT 1")
        .fetch_one(&state.pool)
        .await
        .map(|_| true)
        .unwrap_or(false);
    let worker_ok = match WorkerClient::new(state.worker_base_url.clone()) {
        Ok(c) => c.healthz().await.unwrap_or(false),
        Err(_) => false,
    };
    let body = serde_json::json!({"db_ok": db_ok, "worker_ok": worker_ok});
    if db_ok {
        HttpResponse::Ok().json(body)
    } else {
        HttpResponse::ServiceUnavailable().json(body)
    }
}

// --------------------------- Trigger endpoints ---------------------------

#[derive(Debug, Deserialize, Default)]
struct CreateRunBody {
    #[serde(default = "default_concurrency")]
    concurrency: usize,
    #[serde(default = "default_true")]
    check_drift: bool,
    /// Optional subset. When omitted/null, all distinct SKUs in sales_panel are queued.
    /// When provided, only listed SKUs that exist in sales_panel are queued.
    #[serde(default)]
    skus: Option<Vec<String>>,
}

fn default_concurrency() -> usize { 8 }
fn default_true() -> bool { true }

#[derive(Debug, Serialize)]
struct RunCreated {
    run_id: i64,
    jobs: usize,
    status: &'static str,
}

/// POST /runs — enqueue a monthly run; returns 202 immediately.
#[post("/runs")]
async fn create_run(
    state: Data<AppState>,
    body: Option<Json<CreateRunBody>>,
) -> Result<HttpResponse, ApiError> {
    let body = body.map(|b| b.into_inner()).unwrap_or_default();
    let data_version_hash = sqlx::query_scalar::<_, Option<String>>(
        "SELECT md5(string_agg(sku || '|' || ds::text, ',' ORDER BY sku, ds)) FROM sales_panel",
    )
    .fetch_one(&state.pool)
    .await?
    .unwrap_or_default();
    let config = serde_json::json!({
        "concurrency": body.concurrency,
        "check_drift": body.check_drift,
        "trigger": "api",
        "skus": body.skus,
    });
    let (run_id, n_jobs) = queue::enqueue_monthly_run(
        &state.pool,
        &state.pipeline_version,
        config,
        &data_version_hash,
        body.skus.as_deref(),
    )
    .await
    .map_err(ApiError::from_anyhow)?;

    spawn_run_loop(state.get_ref().clone(), run_id, body.concurrency, body.check_drift);

    Ok(HttpResponse::Accepted().json(RunCreated {
        run_id,
        jobs: n_jobs,
        status: "queued",
    }))
}

/// POST /skus/{sku}/forecast — ad-hoc single-SKU run.
#[post("/skus/{sku}/forecast")]
async fn forecast_sku(
    state: Data<AppState>,
    sku: Path<String>,
) -> Result<HttpResponse, ApiError> {
    let sku = sku.into_inner();
    let data_version_hash = sqlx::query_scalar::<_, Option<String>>(
        "SELECT md5(string_agg(sku || '|' || ds::text, ',' ORDER BY sku, ds)) \
         FROM sales_panel WHERE sku = $1",
    )
    .bind(&sku)
    .fetch_one(&state.pool)
    .await?
    .unwrap_or_default();
    let config = serde_json::json!({
        "concurrency": 1,
        "check_drift": true,
        "trigger": "api",
        "single_sku": &sku,
    });
    let mut tx = state.pool.begin().await?;
    let row = sqlx::query(
        r#"
        INSERT INTO forecast_runs (pipeline_version, data_version_hash, config_json, status)
        VALUES ($1, $2, $3, 'running'::run_status)
        RETURNING run_id
        "#,
    )
    .bind(&state.pipeline_version)
    .bind(&data_version_hash)
    .bind(&config)
    .fetch_one(&mut *tx)
    .await?;
    let run_id: i64 = row.try_get("run_id")?;
    sqlx::query(
        "INSERT INTO forecast_jobs (run_id, sku, status) VALUES ($1, $2, 'queued'::job_status)",
    )
    .bind(run_id)
    .bind(&sku)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;

    spawn_run_loop(state.get_ref().clone(), run_id, 1, true);

    Ok(HttpResponse::Accepted().json(RunCreated {
        run_id,
        jobs: 1,
        status: "queued",
    }))
}

fn spawn_run_loop(state: AppState, run_id: i64, concurrency: usize, check_drift: bool) {
    tokio::spawn(async move {
        let worker = match WorkerClient::new(state.worker_base_url.clone()) {
            Ok(w) => w,
            Err(e) => {
                error!(%run_id, error = %e, "worker client init failed; marking run failed");
                let _ = sqlx::query(
                    "UPDATE forecast_runs SET status = 'failed', completed_at = NOW() WHERE run_id = $1",
                )
                .bind(run_id)
                .execute(&state.pool)
                .await;
                return;
            }
        };
        if let Err(e) = queue::run_monthly(
            &state.pool,
            &worker,
            state.model_dir.clone(),
            state.pipeline_version.clone(),
            run_id,
            concurrency,
            check_drift,
        )
        .await
        {
            error!(%run_id, error = %e, "background run loop failed");
            let _ = sqlx::query(
                "UPDATE forecast_runs SET status = 'failed', completed_at = NOW() WHERE run_id = $1",
            )
            .bind(run_id)
            .execute(&state.pool)
            .await;
        }
    });
}

// --------------------------- Status / query endpoints ---------------------------

#[derive(serde::Deserialize)]
struct ListRunsParams {
    limit: Option<i64>,
}

/// GET /runs — recent forecast runs (newest first) with per-status job counts.
/// Server-authoritative history: every triggered run is visible to all clients,
/// independent of any per-browser local state.
#[get("/runs")]
async fn list_runs(
    state: Data<AppState>,
    q: Query<ListRunsParams>,
) -> Result<HttpResponse, ApiError> {
    let limit = q.limit.unwrap_or(100).clamp(1, 1000);
    let rows = sqlx::query(
        r#"
        SELECT r.run_id,
               r.status::text       AS status,
               r.started_at::text   AS started_at,
               r.completed_at::text AS completed_at,
               r.pipeline_version,
               COALESCE(
                 (SELECT jsonb_object_agg(s.status, s.n)
                  FROM (SELECT status::text AS status, COUNT(*)::int8 AS n
                        FROM forecast_jobs WHERE run_id = r.run_id
                        GROUP BY status) s),
                 '{}'::jsonb
               )::text AS jobs
        FROM forecast_runs r
        ORDER BY r.run_id DESC
        LIMIT $1
        "#,
    )
    .bind(limit)
    .fetch_all(&state.pool)
    .await?;

    let out: Vec<Value> = rows
        .iter()
        .map(|r| -> Result<Value, ApiError> {
            let jobs_txt: String = r.try_get("jobs")?;
            let jobs: Value =
                serde_json::from_str(&jobs_txt).unwrap_or_else(|_| serde_json::json!({}));
            Ok(serde_json::json!({
                "run_id": r.try_get::<i64, _>("run_id")?,
                "status": r.try_get::<String, _>("status")?,
                "started_at": r.try_get::<Option<String>, _>("started_at")?,
                "completed_at": r.try_get::<Option<String>, _>("completed_at")?,
                "pipeline_version": r.try_get::<String, _>("pipeline_version")?,
                "jobs": jobs,
            }))
        })
        .collect::<Result<_, _>>()?;

    Ok(HttpResponse::Ok().json(out))
}

#[get("/runs/{run_id}")]
async fn get_run(
    state: Data<AppState>,
    path: Path<i64>,
) -> Result<HttpResponse, ApiError> {
    let run_id = path.into_inner();
    let run = sqlx::query(
        r#"
        SELECT run_id, status::text AS status, started_at::text AS started_at,
               completed_at::text AS completed_at, pipeline_version
        FROM forecast_runs WHERE run_id = $1
        "#,
    )
    .bind(run_id)
    .fetch_optional(&state.pool)
    .await?
    .ok_or(ApiError::NotFound("run"))?;

    let counts = sqlx::query(
        "SELECT status::text AS status, COUNT(*)::int8 AS n FROM forecast_jobs \
         WHERE run_id = $1 GROUP BY status",
    )
    .bind(run_id)
    .fetch_all(&state.pool)
    .await?;
    let mut jobs = serde_json::Map::new();
    for r in counts {
        let s: String = r.try_get("status")?;
        let n: i64 = r.try_get("n")?;
        jobs.insert(s, Value::from(n));
    }

    Ok(HttpResponse::Ok().json(serde_json::json!({
        "run_id": run.try_get::<i64, _>("run_id")?,
        "status": run.try_get::<String, _>("status")?,
        "started_at": run.try_get::<Option<String>, _>("started_at")?,
        "completed_at": run.try_get::<Option<String>, _>("completed_at")?,
        "pipeline_version": run.try_get::<String, _>("pipeline_version")?,
        "jobs": Value::Object(jobs),
    })))
}

#[get("/runs/{run_id}/skus/{sku}")]
async fn get_run_sku(
    state: Data<AppState>,
    path: Path<(i64, String)>,
) -> Result<HttpResponse, ApiError> {
    let (run_id, sku) = path.into_inner();
    let (run_row, rec) = sku_run_detail(&state.pool, run_id, &sku).await?;
    Ok(HttpResponse::Ok().json(build_sku_run_json(run_id, &sku, run_row, rec)?))
}

#[get("/skus/{sku}/latest")]
async fn get_sku_latest(
    state: Data<AppState>,
    sku: Path<String>,
) -> Result<HttpResponse, ApiError> {
    let sku = sku.into_inner();
    let run_id: i64 = active_run_id(&state.pool, &sku)
        .await?
        .ok_or(ApiError::NotFound("sku"))?;
    let (run_row, rec) = sku_run_detail(&state.pool, run_id, &sku).await?;
    Ok(HttpResponse::Ok().json(build_sku_run_json(run_id, &sku, run_row, rec)?))
}

#[derive(Debug, Deserialize)]
struct HistoryParams {
    limit: Option<i64>,
}

#[get("/skus/{sku}/history")]
async fn get_sku_history(
    state: Data<AppState>,
    sku: Path<String>,
    q: Query<HistoryParams>,
) -> Result<HttpResponse, ApiError> {
    let sku = sku.into_inner();
    let limit = q.limit.unwrap_or(20).clamp(1, 500);
    let rows = sqlx::query(
        r#"
        SELECT sr.run_id, sr.status::text AS status, sr.mode::text AS mode,
               sr.winning_exog, sr.winning_y_variant::text AS winning_y_variant,
               sr.winning_phase::text AS winning_phase,
               sr.winning_mae, sr.completed_at::text AS completed_at,
               rec.starting_stock, rec.cum_demand_q,
               rec.order_qty_rounded
        FROM sku_runs sr
        LEFT JOIN sku_run_recommendation rec
               ON rec.run_id = sr.run_id AND rec.sku = sr.sku
        WHERE sr.sku = $1
        ORDER BY sr.completed_at DESC NULLS LAST, sr.run_id DESC
        LIMIT $2
        "#,
    )
    .bind(&sku)
    .bind(limit)
    .fetch_all(&state.pool)
    .await?;

    let mut out: Vec<Value> = Vec::with_capacity(rows.len());
    for r in rows {
        out.push(serde_json::json!({
            "run_id": r.try_get::<i64, _>("run_id")?,
            "status": r.try_get::<String, _>("status")?,
            "mode": r.try_get::<Option<String>, _>("mode")?,
            "winning_exog": r.try_get::<Option<String>, _>("winning_exog")?,
            "winning_y_variant": r.try_get::<Option<String>, _>("winning_y_variant")?,
            "winning_phase": r.try_get::<Option<String>, _>("winning_phase")?,
            "winning_mae": r.try_get::<Option<f64>, _>("winning_mae")?,
            "completed_at": r.try_get::<Option<String>, _>("completed_at")?,
            "starting_stock": r.try_get::<Option<f64>, _>("starting_stock")?,
            "cum_demand_q": r.try_get::<Option<f64>, _>("cum_demand_q")?,
            "order_qty_rounded": r.try_get::<Option<f64>, _>("order_qty_rounded")?,
        }));
    }
    Ok(HttpResponse::Ok().json(serde_json::json!({"sku": sku, "history": out})))
}

#[derive(Debug, Deserialize)]
struct TimeseriesParams {
    months: Option<i64>,
}

/// GET /skus/{sku}/timeseries?months=24 — recent observed panel points for a SKU.
///
/// Returns the last N month-start rows from `sales_panel` ordered chronologically
/// (oldest first), so the dashboard can render a demand/orders/stock history
/// chart without having to load the full panel. `months` is clamped to [1, 120]
/// and defaults to 24.
#[get("/skus/{sku}/timeseries")]
async fn get_sku_timeseries(
    state: Data<AppState>,
    sku: Path<String>,
    q: Query<TimeseriesParams>,
) -> Result<HttpResponse, ApiError> {
    let sku = sku.into_inner();
    let months = q.months.unwrap_or(24).clamp(1, 120);
    let rows = sqlx::query(
        r#"
        SELECT ds::text AS ds, y, orders, stock
        FROM (
            SELECT ds, y, orders, stock
            FROM sales_panel
            WHERE sku = $1
            ORDER BY ds DESC
            LIMIT $2
        ) recent
        ORDER BY ds ASC
        "#,
    )
    .bind(&sku)
    .bind(months)
    .fetch_all(&state.pool)
    .await?;

    let mut points: Vec<Value> = Vec::with_capacity(rows.len());
    for r in rows {
        points.push(serde_json::json!({
            "ds": r.try_get::<String, _>("ds")?,
            "y": r.try_get::<Option<f64>, _>("y")?,
            "orders": r.try_get::<Option<f64>, _>("orders")?,
            "stock": r.try_get::<Option<f64>, _>("stock")?,
        }));
    }
    Ok(HttpResponse::Ok().json(serde_json::json!({"sku": sku, "points": points})))
}

/// GET /runs/{run_id}/jobs — per-SKU job breakdown for a run.
///
/// Returns one row per forecast_jobs entry: status, attempts, claimed_by,
/// last_error (truncated server-side to keep the payload sane). Used by the
/// RunDetailPage to show which SKUs are queued/running/done/failed instead of
/// just the aggregate counter.
#[get("/runs/{run_id}/jobs")]
async fn get_run_jobs(
    state: Data<AppState>,
    path: Path<i64>,
) -> Result<HttpResponse, ApiError> {
    let run_id = path.into_inner();
    let rows = sqlx::query(
        r#"
        SELECT j.job_id, j.sku,
               j.status::text AS status,
               j.attempts,
               j.claimed_by,
               j.claimed_at::text AS claimed_at,
               LEFT(j.last_error, 2000) AS last_error,
               sr.winning_mae,
               sr.mode::text AS sku_mode
        FROM forecast_jobs j
        LEFT JOIN sku_runs sr ON sr.run_id = j.run_id AND sr.sku = j.sku
        WHERE j.run_id = $1
        ORDER BY
            CASE j.status::text
                WHEN 'failed' THEN 0
                WHEN 'running' THEN 1
                WHEN 'claimed' THEN 2
                WHEN 'queued' THEN 3
                WHEN 'completed' THEN 4
                ELSE 5
            END,
            j.sku
        "#,
    )
    .bind(run_id)
    .fetch_all(&state.pool)
    .await?;

    let mut jobs: Vec<Value> = Vec::with_capacity(rows.len());
    for r in rows {
        jobs.push(serde_json::json!({
            "job_id": r.try_get::<i64, _>("job_id")?,
            "sku": r.try_get::<String, _>("sku")?,
            "status": r.try_get::<String, _>("status")?,
            "attempts": r.try_get::<i32, _>("attempts")?,
            "claimed_by": r.try_get::<Option<String>, _>("claimed_by")?,
            "claimed_at": r.try_get::<Option<String>, _>("claimed_at")?,
            "last_error": r.try_get::<Option<String>, _>("last_error")?,
            "winning_mae": r.try_get::<Option<f64>, _>("winning_mae")?,
            "sku_mode": r.try_get::<Option<String>, _>("sku_mode")?,
        }));
    }
    Ok(HttpResponse::Ok().json(serde_json::json!({
        "run_id": run_id, "jobs": jobs
    })))
}

/// GET /skus/{sku}/predictions — latest completed run's winning-combo trajectory.
///
/// Returns the per-month yhat + bootstrap PI bands so the dashboard can overlay
/// the forecast on the demand history chart. Optional `run_id` query param pins
/// a specific run; otherwise the most recently completed one is used.
#[derive(Debug, Deserialize)]
struct PredictionParams {
    run_id: Option<i64>,
}

#[get("/skus/{sku}/predictions")]
async fn get_sku_predictions(
    state: Data<AppState>,
    sku: Path<String>,
    q: Query<PredictionParams>,
) -> Result<HttpResponse, ApiError> {
    let sku = sku.into_inner();
    let run_id: Option<i64> = match q.run_id {
        Some(id) => Some(id),
        None => active_run_id(&state.pool, &sku).await?,
    };
    let Some(run_id) = run_id else {
        return Ok(HttpResponse::Ok().json(serde_json::json!({
            "sku": sku, "run_id": null, "points": []
        })));
    };

    let rows = sqlx::query(
        r#"
        SELECT ds::text AS ds, y, yhat, pi80_lo, pi80_hi, pi95_lo, pi95_hi
        FROM sku_run_predictions
        WHERE run_id = $1 AND sku = $2
        ORDER BY ds ASC
        "#,
    )
    .bind(run_id)
    .bind(&sku)
    .fetch_all(&state.pool)
    .await?;

    let mut points: Vec<Value> = Vec::with_capacity(rows.len());
    for r in rows {
        points.push(serde_json::json!({
            "ds": r.try_get::<String, _>("ds")?,
            "y": r.try_get::<Option<f64>, _>("y")?,
            "yhat": r.try_get::<f64, _>("yhat")?,
            "pi80_lo": r.try_get::<Option<f64>, _>("pi80_lo")?,
            "pi80_hi": r.try_get::<Option<f64>, _>("pi80_hi")?,
            "pi95_lo": r.try_get::<Option<f64>, _>("pi95_lo")?,
            "pi95_hi": r.try_get::<Option<f64>, _>("pi95_hi")?,
        }));
    }
    Ok(HttpResponse::Ok().json(serde_json::json!({
        "sku": sku, "run_id": run_id, "points": points
    })))
}

/// GET /skus — distinct SKU list known to the backend (from sales_panel).
///
/// The dashboard uses this to keep its SKU count consistent with what the
/// controller will actually queue on `POST /runs`. Returns up to 1000 entries
/// sorted lexicographically.
#[get("/skus")]
async fn list_skus(state: Data<AppState>) -> Result<HttpResponse, ApiError> {
    let rows = sqlx::query_scalar::<_, String>(
        "SELECT DISTINCT sku FROM sales_panel ORDER BY sku LIMIT 1000",
    )
    .fetch_all(&state.pool)
    .await?;
    Ok(HttpResponse::Ok().json(serde_json::json!({"skus": rows})))
}

// --------------------------- Helpers ---------------------------

/// Resolve the active run for a SKU — honour an explicit pin first, otherwise
/// fall back to the most-recently-completed run. Returns None when the SKU
/// has no completed history at all.
async fn active_run_id(pool: &PgPool, sku: &str) -> Result<Option<i64>, ApiError> {
    let row = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT run_id FROM sku_runs
        WHERE sku = $1 AND status = 'completed'
          AND run_id = COALESCE(
              (SELECT pinned_run_id FROM sku_active_pin WHERE sku = $1),
              (SELECT run_id FROM sku_runs
               WHERE sku = $1 AND status = 'completed'
               ORDER BY completed_at DESC NULLS LAST, run_id DESC
               LIMIT 1)
          )
        LIMIT 1
        "#,
    )
    .bind(sku)
    .fetch_optional(pool)
    .await?;
    Ok(row)
}

#[derive(Debug, Deserialize)]
struct SetPinBody {
    run_id: i64,
    pinned_by: Option<String>,
}

/// GET /skus/{sku}/pin — return the currently pinned run for a SKU, if any.
#[get("/skus/{sku}/pin")]
async fn get_sku_pin(
    state: Data<AppState>,
    sku: Path<String>,
) -> Result<HttpResponse, ApiError> {
    let sku = sku.into_inner();
    let row = sqlx::query(
        r#"
        SELECT pinned_run_id, pinned_at::text AS pinned_at, pinned_by
        FROM sku_active_pin WHERE sku = $1
        "#,
    )
    .bind(&sku)
    .fetch_optional(&state.pool)
    .await?;

    if let Some(r) = row {
        Ok(HttpResponse::Ok().json(serde_json::json!({
            "sku": sku,
            "pinned_run_id": r.try_get::<i64, _>("pinned_run_id")?,
            "pinned_at": r.try_get::<Option<String>, _>("pinned_at")?,
            "pinned_by": r.try_get::<Option<String>, _>("pinned_by")?,
        })))
    } else {
        Ok(HttpResponse::Ok().json(serde_json::json!({
            "sku": sku, "pinned_run_id": null
        })))
    }
}

/// POST /skus/{sku}/pin — pin a SKU to a specific historical run. Upserts.
#[post("/skus/{sku}/pin")]
async fn set_sku_pin(
    state: Data<AppState>,
    sku: Path<String>,
    body: Json<SetPinBody>,
) -> Result<HttpResponse, ApiError> {
    let sku = sku.into_inner();
    let body = body.into_inner();

    // Validate the run actually exists and completed for this SKU; otherwise
    // future reads would silently return nothing and confuse the operator.
    let exists: Option<i64> = sqlx::query_scalar(
        "SELECT run_id FROM sku_runs WHERE sku = $1 AND run_id = $2 AND status = 'completed'",
    )
    .bind(&sku)
    .bind(body.run_id)
    .fetch_optional(&state.pool)
    .await?;
    if exists.is_none() {
        return Err(ApiError::BadRequest(
            "pinned run must exist and be completed for this SKU",
        ));
    }

    sqlx::query(
        r#"
        INSERT INTO sku_active_pin (sku, pinned_run_id, pinned_by)
        VALUES ($1, $2, $3)
        ON CONFLICT (sku) DO UPDATE SET
            pinned_run_id = EXCLUDED.pinned_run_id,
            pinned_by = EXCLUDED.pinned_by,
            pinned_at = NOW()
        "#,
    )
    .bind(&sku)
    .bind(body.run_id)
    .bind(body.pinned_by.as_deref())
    .execute(&state.pool)
    .await?;

    Ok(HttpResponse::Ok().json(serde_json::json!({
        "sku": sku, "pinned_run_id": body.run_id
    })))
}

/// DELETE /skus/{sku}/pin — clear the pin, returning to "latest completed" behaviour.
#[delete("/skus/{sku}/pin")]
async fn delete_sku_pin(
    state: Data<AppState>,
    sku: Path<String>,
) -> Result<HttpResponse, ApiError> {
    let sku = sku.into_inner();
    sqlx::query("DELETE FROM sku_active_pin WHERE sku = $1")
        .bind(&sku)
        .execute(&state.pool)
        .await?;
    Ok(HttpResponse::Ok().json(serde_json::json!({"sku": sku, "pinned_run_id": null})))
}

async fn sku_run_detail(
    pool: &PgPool,
    run_id: i64,
    sku: &str,
) -> Result<(sqlx::postgres::PgRow, Option<sqlx::postgres::PgRow>), ApiError> {
    let run_row = sqlx::query(
        r#"
        SELECT sr.status::text AS status, sr.mode::text AS mode,
               sr.winning_horizon::text AS winning_horizon, sr.winning_exog,
               sr.winning_y_variant::text AS winning_y_variant, sr.winning_phase::text AS winning_phase,
               sr.winning_mae, sr.winning_rmse, sr.winning_w_rf, sr.winning_w_xgb,
               sr.p_stockout_3m, sr.p_stockout_6m, sr.e_t_stockout_mo,
               (c.mape / 100.0) AS winning_mape  -- worker stores mape in percent (0-100); normalize to fraction (0-1)
        FROM sku_runs sr
        LEFT JOIN sku_run_combinations c
          ON c.run_id = sr.run_id
         AND c.sku = sr.sku
         AND c.horizon = sr.winning_horizon
         AND c.exog = sr.winning_exog
         AND c.y_variant = sr.winning_y_variant
         AND c.phase = sr.winning_phase
        WHERE sr.run_id = $1 AND sr.sku = $2
        "#,
    )
    .bind(run_id)
    .bind(sku)
    .fetch_optional(pool)
    .await?
    .ok_or(ApiError::NotFound("sku_run"))?;

    let rec = sqlx::query(
        r#"
        SELECT starting_stock, t_check, h_cover, q_target, moq, lot_size,
               cum_demand_q, order_qty_raw, order_qty_rounded
        FROM sku_run_recommendation WHERE run_id = $1 AND sku = $2
        "#,
    )
    .bind(run_id)
    .bind(sku)
    .fetch_optional(pool)
    .await?;

    Ok((run_row, rec))
}

fn build_sku_run_json(
    run_id: i64,
    sku: &str,
    run_row: sqlx::postgres::PgRow,
    rec: Option<sqlx::postgres::PgRow>,
) -> Result<Value, ApiError> {
    let winning = serde_json::json!({
        "horizon": run_row.try_get::<Option<String>, _>("winning_horizon")?,
        "exog": run_row.try_get::<Option<String>, _>("winning_exog")?,
        "y_variant": run_row.try_get::<Option<String>, _>("winning_y_variant")?,
        "phase": run_row.try_get::<Option<String>, _>("winning_phase")?,
        "mae": run_row.try_get::<Option<f64>, _>("winning_mae")?,
        "rmse": run_row.try_get::<Option<f64>, _>("winning_rmse")?,
        "mape": run_row.try_get::<Option<f64>, _>("winning_mape")?,
        "w_rf": run_row.try_get::<Option<f64>, _>("winning_w_rf")?,
        "w_xgb": run_row.try_get::<Option<f64>, _>("winning_w_xgb")?,
        "p_stockout_3m": run_row.try_get::<Option<f64>, _>("p_stockout_3m")?,
        "p_stockout_6m": run_row.try_get::<Option<f64>, _>("p_stockout_6m")?,
        "e_t_stockout_mo": run_row.try_get::<Option<f64>, _>("e_t_stockout_mo")?,
    });
    let mut out = serde_json::Map::new();
    out.insert("run_id".into(), Value::from(run_id));
    out.insert("sku".into(), Value::from(sku.to_string()));
    out.insert("status".into(), Value::from(run_row.try_get::<String, _>("status")?));
    out.insert("mode".into(), Value::from(run_row.try_get::<String, _>("mode")?));
    out.insert("winning".into(), winning);
    if let Some(rec) = rec {
        let rec_json = serde_json::json!({
            "starting_stock": rec.try_get::<Option<f64>, _>("starting_stock")?,
            "t_check": rec.try_get::<Option<i32>, _>("t_check")?,
            "h_cover": rec.try_get::<Option<i32>, _>("h_cover")?,
            "q_target": rec.try_get::<Option<f64>, _>("q_target")?,
            "moq": rec.try_get::<Option<f64>, _>("moq")?,
            "lot_size": rec.try_get::<Option<f64>, _>("lot_size")?,
            "cum_demand_q": rec.try_get::<Option<f64>, _>("cum_demand_q")?,
            "order_qty_raw": rec.try_get::<Option<f64>, _>("order_qty_raw")?,
            "order_qty_rounded": rec.try_get::<Option<f64>, _>("order_qty_rounded")?,
        });
        out.insert("recommendation".into(), rec_json);
    }
    Ok(Value::Object(out))
}

// --------------------------- Error type ---------------------------

/// Mirrors Stockimg-AI `public-api/src/error.rs` shape (thiserror + ResponseError).
#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("Internal Server Error: {0}")]
    Internal(String),
    #[error("Bad Request: {0}")]
    BadRequest(&'static str),
    #[error("{0} not found")]
    NotFound(&'static str),
}

impl ApiError {
    pub fn from_anyhow(e: anyhow::Error) -> Self { Self::Internal(format!("{e:#}")) }
}

impl From<sqlx::Error> for ApiError {
    fn from(e: sqlx::Error) -> Self { Self::Internal(format!("sqlx: {e}")) }
}

impl ResponseError for ApiError {
    fn status_code(&self) -> actix_web::http::StatusCode {
        use actix_web::http::StatusCode;
        match self {
            ApiError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
            ApiError::BadRequest(_) => StatusCode::BAD_REQUEST,
            ApiError::NotFound(_) => StatusCode::NOT_FOUND,
        }
    }
    fn error_response(&self) -> HttpResponse {
        HttpResponse::build(self.status_code())
            .json(serde_json::json!({"error": self.to_string()}))
    }
}
