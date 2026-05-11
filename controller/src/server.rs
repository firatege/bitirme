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
    get, post,
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
            .service(get_run)
            .service(get_run_sku)
            .service(forecast_sku)
            .service(get_sku_latest)
            .service(get_sku_history)
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
    let row = sqlx::query(
        r#"
        SELECT run_id FROM sku_runs WHERE sku = $1 AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST, run_id DESC LIMIT 1
        "#,
    )
    .bind(&sku)
    .fetch_optional(&state.pool)
    .await?;
    let run_id: i64 = row
        .ok_or(ApiError::NotFound("sku"))?
        .try_get("run_id")?;
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
        SELECT run_id, status::text AS status, mode::text AS mode,
               winning_exog, winning_y_variant::text AS winning_y_variant,
               winning_phase::text AS winning_phase, winning_mae, completed_at::text AS completed_at
        FROM sku_runs WHERE sku = $1
        ORDER BY completed_at DESC NULLS LAST, run_id DESC
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
        }));
    }
    Ok(HttpResponse::Ok().json(serde_json::json!({"sku": sku, "history": out})))
}

// --------------------------- Helpers ---------------------------

async fn sku_run_detail(
    pool: &PgPool,
    run_id: i64,
    sku: &str,
) -> Result<(sqlx::postgres::PgRow, Option<sqlx::postgres::PgRow>), ApiError> {
    let run_row = sqlx::query(
        r#"
        SELECT status::text AS status, mode::text AS mode,
               winning_horizon::text AS winning_horizon, winning_exog,
               winning_y_variant::text AS winning_y_variant, winning_phase::text AS winning_phase,
               winning_mae, winning_rmse, winning_w_rf, winning_w_xgb,
               p_stockout_3m, p_stockout_6m, e_t_stockout_mo
        FROM sku_runs WHERE run_id = $1 AND sku = $2
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
