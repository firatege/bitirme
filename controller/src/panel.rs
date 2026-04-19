//! CSV ingest for sales_panel + sku_config. Idempotent via ON CONFLICT upserts.

use anyhow::{Context, Result};
use csv::ReaderBuilder;
use sqlx::PgPool;
use std::path::Path;
use time::format_description::BorrowedFormatItem;
use time::macros::format_description;
use time::Date;
use tracing::{info, warn};

const CHUNK: usize = 2000;

const DATE_FORMATS: &[&[BorrowedFormatItem<'static>]] = &[
    format_description!("[year]-[month]-[day]"),
    format_description!("[year]/[month]/[day]"),
];

fn parse_date(s: &str) -> Result<Date> {
    for fmt in DATE_FORMATS {
        if let Ok(d) = Date::parse(s, fmt) {
            return Ok(d);
        }
    }
    anyhow::bail!("unrecognized date: {s}")
}

pub async fn seed_panel(pool: &PgPool, path: &Path) -> Result<usize> {
    let mut rdr = ReaderBuilder::new().from_path(path).with_context(|| format!("open {}", path.display()))?;
    let headers = rdr.headers()?.clone();
    let ix = |name: &str| -> Result<usize> {
        headers
            .iter()
            .position(|h| h == name)
            .with_context(|| format!("column `{name}` missing from {}", path.display()))
    };
    let i_sku = ix("sku")?;
    let i_ds = ix("ds")?;
    let i_y = ix("y")?;
    let i_orders = ix("orders")?;
    let i_stock = ix("stock")?;

    let mut skus: Vec<String> = Vec::with_capacity(CHUNK);
    let mut dss: Vec<Date> = Vec::with_capacity(CHUNK);
    let mut ys: Vec<f64> = Vec::with_capacity(CHUNK);
    let mut ords: Vec<f64> = Vec::with_capacity(CHUNK);
    let mut stks: Vec<f64> = Vec::with_capacity(CHUNK);

    let mut total = 0usize;

    for rec in rdr.records() {
        let rec = rec?;
        skus.push(rec.get(i_sku).unwrap_or("").to_string());
        dss.push(parse_date(rec.get(i_ds).unwrap_or(""))?);
        ys.push(rec.get(i_y).unwrap_or("0").parse().unwrap_or(0.0));
        ords.push(rec.get(i_orders).unwrap_or("0").parse().unwrap_or(0.0));
        stks.push(rec.get(i_stock).unwrap_or("0").parse().unwrap_or(0.0));

        if skus.len() >= CHUNK {
            total += flush_panel(pool, &skus, &dss, &ys, &ords, &stks).await?;
            skus.clear(); dss.clear(); ys.clear(); ords.clear(); stks.clear();
        }
    }
    if !skus.is_empty() {
        total += flush_panel(pool, &skus, &dss, &ys, &ords, &stks).await?;
    }
    info!(rows = total, "sales_panel upserted");
    Ok(total)
}

async fn flush_panel(
    pool: &PgPool,
    skus: &[String],
    dss: &[Date],
    ys: &[f64],
    ords: &[f64],
    stks: &[f64],
) -> Result<usize> {
    let q = r#"
        INSERT INTO sales_panel (sku, ds, y, orders, stock)
        SELECT * FROM UNNEST($1::text[], $2::date[], $3::float8[], $4::float8[], $5::float8[])
        ON CONFLICT (sku, ds) DO UPDATE
          SET y = EXCLUDED.y, orders = EXCLUDED.orders, stock = EXCLUDED.stock
    "#;
    sqlx::query(q)
        .bind(skus)
        .bind(dss)
        .bind(ys)
        .bind(ords)
        .bind(stks)
        .execute(pool)
        .await
        .context("upsert sales_panel")?;
    Ok(skus.len())
}

pub async fn seed_config(pool: &PgPool, path: &Path) -> Result<usize> {
    let mut rdr = ReaderBuilder::new().from_path(path).with_context(|| format!("open {}", path.display()))?;
    let headers = rdr.headers()?.clone();
    let ix = |name: &str| -> Result<usize> {
        headers
            .iter()
            .position(|h| h == name)
            .with_context(|| format!("column `{name}` missing from {}", path.display()))
    };
    let i_sku = ix("sku")?;
    let i_tc = ix("T_CHECK")?;
    let i_hc = ix("H_COVER")?;
    let i_qt = ix("q_target")?;
    let i_lt = ix("lead_time_mo")?;
    let i_moq = ix("MOQ")?;
    let i_lot = ix("lot_size")?;

    let mut n = 0usize;
    for rec in rdr.records() {
        let rec = rec?;
        let q = r#"
            INSERT INTO sku_config (sku, t_check, h_cover, q_target, lead_time_mo, moq, lot_size, starting_stock_override)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NULL)
            ON CONFLICT (sku) DO UPDATE SET
                t_check = EXCLUDED.t_check,
                h_cover = EXCLUDED.h_cover,
                q_target = EXCLUDED.q_target,
                lead_time_mo = EXCLUDED.lead_time_mo,
                moq = EXCLUDED.moq,
                lot_size = EXCLUDED.lot_size
        "#;
        let res = sqlx::query(q)
            .bind(rec.get(i_sku).unwrap_or(""))
            .bind::<i32>(rec.get(i_tc).unwrap_or("0").parse().unwrap_or(0))
            .bind::<i32>(rec.get(i_hc).unwrap_or("0").parse().unwrap_or(0))
            .bind::<f64>(rec.get(i_qt).unwrap_or("0").parse().unwrap_or(0.0))
            .bind::<i32>(rec.get(i_lt).unwrap_or("0").parse().unwrap_or(0))
            .bind::<f64>(rec.get(i_moq).unwrap_or("0").parse().unwrap_or(0.0))
            .bind::<f64>(rec.get(i_lot).unwrap_or("1").parse().unwrap_or(1.0))
            .execute(pool)
            .await;
        match res {
            Ok(_) => n += 1,
            Err(e) => warn!(error = %e, "sku_config row failed"),
        }
    }
    info!(rows = n, "sku_config upserted");
    Ok(n)
}
