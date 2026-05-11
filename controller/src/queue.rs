//! Job queue backed by forecast_jobs. Claim pattern: FOR UPDATE SKIP LOCKED.

use anyhow::{Context, Result};
use sqlx::{PgPool, Row};
use std::time::Duration;
use tracing::{info, warn};

use crate::api::WorkerClient;
use crate::orchestrator::Orchestrator;

pub const MAX_ATTEMPTS: i32 = 2;

/// Create a new forecast_runs row and enqueue one forecast_jobs row per SKU.
/// If `skus` is `None`, every distinct SKU in sales_panel is enqueued (full monthly run).
/// If `skus` is `Some(list)`, only those that exist in sales_panel are enqueued — unknown
/// SKUs are silently dropped via the INNER JOIN (a future revision can return a 4xx with
/// the missing set if needed). Returns (run_id, total_jobs).
pub async fn enqueue_monthly_run(
    pool: &PgPool,
    pipeline_version: &str,
    config_json: serde_json::Value,
    data_version_hash: &str,
    skus: Option<&[String]>,
) -> Result<(i64, usize)> {
    let mut tx = pool.begin().await?;
    let row = sqlx::query(
        r#"
        INSERT INTO forecast_runs (pipeline_version, data_version_hash, config_json, status)
        VALUES ($1, $2, $3, 'running'::run_status)
        RETURNING run_id
        "#,
    )
    .bind(pipeline_version)
    .bind(data_version_hash)
    .bind(&config_json)
    .fetch_one(&mut *tx)
    .await
    .context("INSERT forecast_runs")?;
    let run_id: i64 = row.try_get("run_id")?;

    let inserted = match skus {
        None => {
            sqlx::query(
                r#"
                INSERT INTO forecast_jobs (run_id, sku, status)
                SELECT $1, sku, 'queued'::job_status FROM (
                    SELECT DISTINCT sku FROM sales_panel ORDER BY sku
                ) AS s
                ON CONFLICT (run_id, sku) DO NOTHING
                "#,
            )
            .bind(run_id)
            .execute(&mut *tx)
            .await
            .context("INSERT forecast_jobs")?
        }
        Some(filter) => {
            // INNER JOIN against sales_panel so unknown SKUs are dropped (no silent
            // "queued forever" rows).
            sqlx::query(
                r#"
                INSERT INTO forecast_jobs (run_id, sku, status)
                SELECT $1, p.sku, 'queued'::job_status
                FROM (SELECT DISTINCT sku FROM sales_panel) AS p
                JOIN unnest($2::text[]) AS req(sku) USING (sku)
                ORDER BY p.sku
                ON CONFLICT (run_id, sku) DO NOTHING
                "#,
            )
            .bind(run_id)
            .bind(filter)
            .execute(&mut *tx)
            .await
            .context("INSERT forecast_jobs (filtered)")?
        }
    };

    tx.commit().await?;
    Ok((run_id, inserted.rows_affected() as usize))
}

/// Try to claim one queued job for `run_id`. Returns the SKU if one was claimed.
/// Uses FOR UPDATE SKIP LOCKED so parallel workers don't pick the same row.
pub async fn claim_one(pool: &PgPool, run_id: i64, worker_id: &str) -> Result<Option<(i64, String)>> {
    let mut tx = pool.begin().await?;
    let row = sqlx::query(
        r#"
        SELECT job_id, sku FROM forecast_jobs
        WHERE run_id = $1 AND status = 'queued'::job_status
        ORDER BY job_id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
        "#,
    )
    .bind(run_id)
    .fetch_optional(&mut *tx)
    .await?;

    let Some(row) = row else {
        tx.commit().await?;
        return Ok(None);
    };
    let job_id: i64 = row.try_get("job_id")?;
    let sku: String = row.try_get("sku")?;

    sqlx::query(
        r#"
        UPDATE forecast_jobs
        SET status = 'claimed'::job_status, claimed_by = $2, claimed_at = NOW(),
            attempts = attempts + 1
        WHERE job_id = $1
        "#,
    )
    .bind(job_id)
    .bind(worker_id)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(Some((job_id, sku)))
}

pub async fn mark_completed(pool: &PgPool, job_id: i64) -> Result<()> {
    sqlx::query("UPDATE forecast_jobs SET status = 'completed'::job_status WHERE job_id = $1")
        .bind(job_id)
        .execute(pool)
        .await?;
    Ok(())
}

/// Bump attempts; either requeue (< MAX_ATTEMPTS) or mark failed.
pub async fn mark_failed_or_requeue(pool: &PgPool, job_id: i64, error: &str) -> Result<()> {
    let row = sqlx::query(
        "SELECT attempts FROM forecast_jobs WHERE job_id = $1",
    )
    .bind(job_id)
    .fetch_one(pool)
    .await?;
    let attempts: i32 = row.try_get("attempts")?;
    if attempts < MAX_ATTEMPTS {
        sqlx::query(
            r#"
            UPDATE forecast_jobs
            SET status = 'queued'::job_status, last_error = $2, claimed_by = NULL, claimed_at = NULL
            WHERE job_id = $1
            "#,
        )
        .bind(job_id)
        .bind(error)
        .execute(pool)
        .await?;
        warn!(job_id, attempts, "requeued after error");
    } else {
        sqlx::query(
            "UPDATE forecast_jobs SET status = 'failed'::job_status, last_error = $2 WHERE job_id = $1",
        )
        .bind(job_id)
        .bind(error)
        .execute(pool)
        .await?;
        warn!(job_id, attempts, "marked failed (exceeded MAX_ATTEMPTS)");
    }
    Ok(())
}

/// Mark the forecast_runs row completed once every job is completed-or-failed.
pub async fn finalize_run_if_done(pool: &PgPool, run_id: i64) -> Result<bool> {
    let row = sqlx::query(
        r#"
        SELECT COUNT(*) FILTER (WHERE status NOT IN ('completed','failed')) AS open_count
        FROM forecast_jobs WHERE run_id = $1
        "#,
    )
    .bind(run_id)
    .fetch_one(pool)
    .await?;
    let open: i64 = row.try_get("open_count")?;
    if open == 0 {
        sqlx::query(
            "UPDATE forecast_runs SET completed_at = NOW(), status = 'completed' WHERE run_id = $1",
        )
        .bind(run_id)
        .execute(pool)
        .await?;
        return Ok(true);
    }
    Ok(false)
}

/// Main claim loop. Spawns `concurrency` tokio tasks that each poll claim_one,
/// dispatch via orchestrator.run_single_sku, and update job state.
pub async fn run_monthly(
    pool: &PgPool,
    worker: &WorkerClient,
    model_dir: std::path::PathBuf,
    pipeline_version: String,
    run_id: i64,
    concurrency: usize,
    check_drift: bool,
) -> Result<()> {
    let mut handles: Vec<tokio::task::JoinHandle<()>> = Vec::with_capacity(concurrency);
    let pool = pool.clone();
    let base_url = worker.base_url().to_string();

    for w in 0..concurrency {
        let worker_id = format!("w{w}");
        let pool_c = pool.clone();
        let model_dir_c = model_dir.clone();
        let pipeline_version_c = pipeline_version.clone();
        let base_url_c = base_url.clone();
        handles.push(tokio::spawn(async move {
            let worker = match WorkerClient::new(base_url_c) {
                Ok(w) => w,
                Err(e) => { tracing::error!(error = %e, "worker client init"); return; }
            };
            let orch = Orchestrator {
                pool: &pool_c,
                worker: &worker,
                model_dir: model_dir_c,
                pipeline_version: pipeline_version_c,
            };
            loop {
                let claim = match claim_one(&pool_c, run_id, &worker_id).await {
                    Ok(c) => c,
                    Err(e) => {
                        tracing::error!(error = %e, "claim_one");
                        tokio::time::sleep(Duration::from_millis(500)).await;
                        continue;
                    }
                };
                let Some((job_id, sku)) = claim else { break };
                info!(worker_id = %worker_id, sku = %sku, job_id, "claimed");
                match orch.dispatch_for_run(run_id, &sku, check_drift).await {
                    Ok(()) => {
                        if let Err(e) = mark_completed(&pool_c, job_id).await {
                            tracing::error!(error = %e, "mark_completed");
                        }
                        info!(worker_id = %worker_id, sku = %sku, run_id, "done");
                    }
                    Err(e) => {
                        let msg = format!("{e:#}");
                        tracing::error!(worker_id = %worker_id, sku = %sku, error = %msg, "dispatch failed");
                        if let Err(e2) = mark_failed_or_requeue(&pool_c, job_id, &msg).await {
                            tracing::error!(error = %e2, "mark_failed_or_requeue");
                        }
                    }
                }
            }
        }));
    }

    futures::future::join_all(handles).await;
    finalize_run_if_done(&pool, run_id).await?;
    Ok(())
}
