//! Postgres connection + embedded sqlx migrations.
//!
//! Adapted from Stockimg-AI `shared/rust/src/utils/database.rs`. Differences from
//! the original:
//!   * Returns `sqlx::PgPool` instead of `sea_orm::DatabaseConnection` — we haven't
//!     pulled SeaORM in yet (Phase 2 deferred due to 2.0.0-rc.18 feature-flag issue).
//!     Swapping to `sea_orm::Database::connect(&url)` is a one-line change when we
//!     re-add that dep.
//!   * Uses `tracing` instead of `log`.
//!
//! Both PG_HOST/PG_USER/PG_PASS/PG_DATABASE env vars *and* DATABASE_URL are supported;
//! the PG_* variant wins if all four are set (used by CNPG / k8s secret mounts in the
//! Stockimg setup).

use anyhow::{Context, Result};
use sqlx::migrate::Migrator;
use sqlx::postgres::PgPoolOptions;
use sqlx::{Executor, PgPool};
use std::path::Path;
use tracing::info;

/// Database connection parameters.
struct DbParams {
    host: String,
    port: String,
    user: String,
    pass: String,
    database: String,
}

impl DbParams {
    fn url(&self, database: &str) -> String {
        let encoded_pass = urlencoding::encode(&self.pass);
        format!(
            "postgresql://{}:{}@{}:{}/{}",
            self.user, encoded_pass, self.host, self.port, database
        )
    }

    fn target_url(&self) -> String {
        self.url(&self.database)
    }

    fn admin_url(&self) -> String {
        self.url("postgres")
    }
}

/// Priority:
/// 1. If PG_HOST, PG_USER, PG_PASS, PG_DATABASE are set → use them directly.
/// 2. Otherwise → parse DATABASE_URL into parts.
fn get_db_params() -> Result<DbParams> {
    let pg_host = std::env::var("PG_HOST");
    let pg_user = std::env::var("PG_USER");
    let pg_pass = std::env::var("PG_PASS");
    let pg_database = std::env::var("PG_DATABASE");
    let pg_port = std::env::var("PG_PORT").unwrap_or_else(|_| "5432".to_string());

    if let (Ok(host), Ok(user), Ok(pass), Ok(database)) = (pg_host, pg_user, pg_pass, pg_database) {
        info!(host = %host, db = %database, "using PG_* env vars");
        return Ok(DbParams { host, port: pg_port, user, pass, database });
    }

    let url = std::env::var("DATABASE_URL")
        .context("neither PG_* vars nor DATABASE_URL are set")?;
    parse_database_url(&url)
}

/// Parses a PostgreSQL URL into its components.
fn parse_database_url(url: &str) -> Result<DbParams> {
    let without_protocol = url
        .strip_prefix("postgresql://")
        .or_else(|| url.strip_prefix("postgres://"))
        .context("invalid database URL: must start with postgresql:// or postgres://")?;

    let (credentials, rest) = without_protocol
        .split_once('@')
        .context("invalid database URL: missing @ separator")?;

    let (user, pass) = credentials
        .split_once(':')
        .context("invalid database URL: missing password")?;

    let (host_port, database) = rest
        .split_once('/')
        .context("invalid database URL: missing database name")?;

    // Strip query params off the database name if present.
    let database = database.split('?').next().unwrap_or(database);

    let (host, port) = if let Some((h, p)) = host_port.split_once(':') {
        (h.to_string(), p.to_string())
    } else {
        (host_port.to_string(), "5432".to_string())
    };

    // URL-decode the password (host-level special chars like @ / : can be pct-encoded).
    let pass = urlencoding::decode(pass)
        .map(|s| s.into_owned())
        .unwrap_or_else(|_| pass.to_string());

    info!(host = %host, db = %database, "parsed DATABASE_URL");
    Ok(DbParams {
        host,
        port,
        user: user.to_string(),
        pass,
        database: database.to_string(),
    })
}

/// Admin-connects to the `postgres` database and CREATE the target DB if missing.
async fn ensure_database_exists(params: &DbParams) -> Result<()> {
    info!(db = %params.database, "checking if database exists");

    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(&params.admin_url())
        .await
        .context("connect postgres admin DB")?;

    let exists: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = $1)",
    )
    .bind(&params.database)
    .fetch_one(&pool)
    .await?;

    if exists {
        info!(db = %params.database, "database already exists");
    } else {
        info!(db = %params.database, "creating database");
        // CREATE DATABASE can't take parameters. DB name is controlled by config, not user input.
        let quoted = params.database.replace('"', "\"\"");
        pool.execute(format!("CREATE DATABASE \"{quoted}\"").as_str())
            .await
            .context("CREATE DATABASE")?;
        info!(db = %params.database, "database created");
    }

    pool.close().await;
    Ok(())
}

/// Runs sqlx migrations from the given directory.
async fn run_migrations(database_url: &str, migrations_path: &str) -> Result<()> {
    info!(path = %migrations_path, "running migrations");
    let pool = PgPool::connect(database_url)
        .await
        .context("connect for migrations")?;
    let migrator = Migrator::new(Path::new(migrations_path))
        .await
        .with_context(|| format!("load migrations from {migrations_path}"))?;
    migrator.run(&pool).await.context("run migrations")?;
    info!("migrations completed successfully");
    pool.close().await;
    Ok(())
}

/// Connects to the target DB, creating it if missing and applying pending migrations.
///
/// `migrations_path` can be overridden by the `MIGRATIONS_PATH` env var (useful in
/// container setups where the CWD differs between dev and prod).
pub async fn connect_database_with_migrations(migrations_path: &str) -> Result<PgPool> {
    let params = get_db_params()?;
    ensure_database_exists(&params).await?;

    let migrations_path = std::env::var("MIGRATIONS_PATH").unwrap_or_else(|_| migrations_path.to_string());
    run_migrations(&params.target_url(), &migrations_path).await?;

    let pool = PgPoolOptions::new()
        .max_connections(8)
        .connect(&params.target_url())
        .await
        .context("connect target database pool")?;
    info!(db = %params.database, "connected");
    Ok(pool)
}

/// Connect without running migrations. Used by read-only commands (status, backfill).
pub async fn connect_database() -> Result<PgPool> {
    let params = get_db_params()?;
    ensure_database_exists(&params).await?;
    let pool = PgPoolOptions::new()
        .max_connections(4)
        .connect(&params.target_url())
        .await
        .context("connect target database pool")?;
    info!(db = %params.database, "connected (no migrations)");
    Ok(pool)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_database_url_basic() {
        let params = parse_database_url("postgresql://user:pass@localhost:5432/mydb").unwrap();
        assert_eq!(params.user, "user");
        assert_eq!(params.pass, "pass");
        assert_eq!(params.host, "localhost");
        assert_eq!(params.port, "5432");
        assert_eq!(params.database, "mydb");
    }

    #[test]
    fn parse_database_url_default_port() {
        let params = parse_database_url("postgres://user:pass@localhost/payment").unwrap();
        assert_eq!(params.host, "localhost");
        assert_eq!(params.port, "5432");
        assert_eq!(params.database, "payment");
    }

    #[test]
    fn parse_database_url_strips_query_params() {
        let params =
            parse_database_url("postgres://user:pass@host/payment?sslmode=disable").unwrap();
        assert_eq!(params.database, "payment");
    }

    #[test]
    fn parse_database_url_decodes_password() {
        let params = parse_database_url("postgresql://user:p%40ss%2Fword@localhost/db").unwrap();
        assert_eq!(params.pass, "p@ss/word");
    }

    #[test]
    fn db_params_encodes_password_in_url() {
        let params = DbParams {
            host: "localhost".to_string(),
            port: "5432".to_string(),
            user: "user".to_string(),
            pass: "p@ss".to_string(),
            database: "mydb".to_string(),
        };
        assert_eq!(
            params.target_url(),
            "postgresql://user:p%40ss@localhost:5432/mydb"
        );
        assert_eq!(
            params.admin_url(),
            "postgresql://user:p%40ss@localhost:5432/postgres"
        );
    }
}
