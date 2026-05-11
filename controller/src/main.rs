//! controller — Rust orchestrator. Owns Postgres; dispatches forecast jobs to the Python
//! worker over HTTP; writes results transactionally.

use controller::{api, db, orchestrator, panel, queue, server};

use anyhow::Result;
use clap::{Parser, Subcommand};
use std::path::PathBuf;
use tracing::info;
use tracing_subscriber::EnvFilter;

#[derive(Parser, Debug)]
#[command(name = "controller", version, about = "Bitirme forecast orchestrator")]
struct Cli {
    /// Python worker base URL.
    #[arg(long, env = "API_URL", default_value = "http://localhost:8000")]
    api_url: String,

    /// Root directory for joblib model blobs (mounted from models_data volume in Compose).
    #[arg(long, env = "MODEL_DIR", default_value = "/app/models")]
    model_dir: PathBuf,

    /// Directory containing sqlx migrations. Can be overridden by MIGRATIONS_PATH env.
    #[arg(long, default_value = "controller/migrations")]
    migrations: PathBuf,

    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand, Debug)]
enum Cmd {
    /// Run pending sqlx migrations and exit.
    Migrate,
    /// One-shot bootstrap: load panel + config CSVs into Postgres (idempotent upserts).
    Seed {
        #[arg(long)]
        panel: PathBuf,
        #[arg(long)]
        config: PathBuf,
    },
    /// Monthly incremental panel append.
    IngestPanel {
        #[arg(long)]
        panel: PathBuf,
    },
    /// Forecast for a single SKU. By default chooses warm-or-cold based on DB state.
    SingleSku {
        sku: String,
        /// Force cold path (ignore any cached prior run).
        #[arg(long)]
        cold: bool,
        /// Skip the drift gate and always go warm when a prior run exists.
        #[arg(long)]
        no_drift_check: bool,
    },
    /// Dump run progress.
    Status {
        run_id: i64,
    },
    /// Rebuild the CachedSpec JSON for a SKU (from the latest completed run) and print it.
    /// Useful for debugging warm-path inputs without dispatching to the API.
    BackfillCachedSpec {
        sku: String,
    },
    /// Monthly run — full panel via parallel claim loop.
    MonthlyRun {
        /// Concurrent forecast dispatchers (tokio tasks).
        #[arg(long, env = "MAX_PARALLEL_JOBS", default_value_t = 8)]
        concurrency: usize,
        /// Skip the drift gate; always go warm when a prior run exists.
        #[arg(long)]
        no_drift_check: bool,
    },
    /// Start the HTTP REST API. Internal-only; no auth.
    Serve {
        /// Bind address (host:port).
        #[arg(long, env = "CONTROLLER_BIND", default_value = "0.0.0.0:9000")]
        bind: String,
    },
}

fn init_tracing() {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,sqlx=warn"));
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(false)
        .init();
}

fn pipeline_version() -> String {
    concat!("controller@", env!("CARGO_PKG_VERSION")).to_string()
}

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing();
    let cli = Cli::parse();
    let migrations_path = cli.migrations.to_string_lossy().into_owned();

    match cli.cmd {
        Cmd::Migrate => {
            let pool = db::connect_database_with_migrations(&migrations_path).await?;
            info!("migrations applied");
            drop(pool);
        }
        Cmd::Seed { panel, config } => {
            let pool = db::connect_database_with_migrations(&migrations_path).await?;
            let np = panel::seed_panel(&pool, &panel).await?;
            let nc = panel::seed_config(&pool, &config).await?;
            info!(panel_rows = np, config_rows = nc, "seed complete");
        }
        Cmd::IngestPanel { panel } => {
            let pool = db::connect_database_with_migrations(&migrations_path).await?;
            let n = panel::seed_panel(&pool, &panel).await?;
            info!(panel_rows = n, "ingest complete");
        }
        Cmd::SingleSku { sku, cold, no_drift_check } => {
            let pool = db::connect_database_with_migrations(&migrations_path).await?;
            let worker = api::WorkerClient::new(cli.api_url.clone())?;
            let orch = orchestrator::Orchestrator {
                pool: &pool,
                worker: &worker,
                model_dir: cli.model_dir.clone(),
                pipeline_version: pipeline_version(),
            };
            let run_id = if cold {
                orch.run_single_sku_cold(&sku).await?
            } else {
                orch.run_single_sku(&sku, !no_drift_check).await?
            };
            info!(sku = %sku, run_id, "single-sku run complete");
        }
        Cmd::Status { run_id } => {
            let pool = db::connect_database().await?;
            // Job-queue progress summary
            let counts: Vec<(String, i64)> = sqlx::query_as(
                "SELECT status::text, COUNT(*) AS n FROM forecast_jobs WHERE run_id = $1 GROUP BY status",
            )
            .bind(run_id)
            .fetch_all(&pool)
            .await?;
            println!("== forecast_jobs (run {run_id}) ==");
            for (s, n) in &counts {
                println!("  {s}: {n}");
            }
            // Per-SKU detail
            println!("== sku_runs ==");
            let rows = sqlx::query_as::<_, (String, String, Option<String>, Option<String>, Option<String>, Option<f64>)>(
                "SELECT sku, status::text, mode::text, winning_exog, winning_y_variant::text, winning_mae \
                 FROM sku_runs WHERE run_id = $1 ORDER BY sku",
            )
            .bind(run_id)
            .fetch_all(&pool)
            .await?;
            for (sku, status, mode, exog, variant, mae) in rows {
                println!(
                    "  {sku}\t{status}\t{}\t{}\t{}\t{}",
                    mode.unwrap_or_default(),
                    exog.unwrap_or_default(),
                    variant.unwrap_or_default(),
                    mae.map(|v| format!("{v:.3}")).unwrap_or_default(),
                );
            }
        }
        Cmd::BackfillCachedSpec { sku } => {
            let pool = db::connect_database().await?;
            let spec = controller::cached_spec::load_latest(&pool, &sku).await?;
            match spec {
                Some(s) => {
                    println!("{}", serde_json::to_string_pretty(&s)?);
                }
                None => {
                    eprintln!("no completed prior run for sku {sku}");
                    std::process::exit(1);
                }
            }
        }
        Cmd::Serve { bind } => {
            let pool = db::connect_database_with_migrations(&migrations_path).await?;
            let state = server::AppState {
                pool,
                worker_base_url: cli.api_url.clone(),
                model_dir: cli.model_dir.clone(),
                pipeline_version: pipeline_version(),
            };
            let addr: std::net::SocketAddr = bind
                .parse()
                .map_err(|e| anyhow::anyhow!("invalid CONTROLLER_BIND `{bind}`: {e}"))?;
            server::serve(addr, state).await?;
        }
        Cmd::MonthlyRun { concurrency, no_drift_check } => {
            let pool = db::connect_database_with_migrations(&migrations_path).await?;
            let worker = api::WorkerClient::new(cli.api_url.clone())?;
            let data_version_hash = sqlx::query_scalar::<_, Option<String>>(
                "SELECT md5(string_agg(sku || '|' || ds::text, ',' ORDER BY sku, ds)) FROM sales_panel"
            )
            .fetch_one(&pool)
            .await?
            .unwrap_or_default();
            let config = serde_json::json!({
                "concurrency": concurrency,
                "check_drift": !no_drift_check,
            });
            let (run_id, n_jobs) = queue::enqueue_monthly_run(
                &pool, &pipeline_version(), config, &data_version_hash, None,
            ).await?;
            info!(run_id, n_jobs, concurrency, "monthly-run enqueued; starting claim loop");
            queue::run_monthly(
                &pool,
                &worker,
                cli.model_dir.clone(),
                pipeline_version(),
                run_id,
                concurrency,
                !no_drift_check,
            ).await?;
            info!(run_id, "monthly-run complete");
        }
    }
    Ok(())
}
