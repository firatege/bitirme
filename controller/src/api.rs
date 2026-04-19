//! Reqwest client for the Python worker. 30-minute timeout covers the ~5-minute
//! worst-case per-SKU fit with generous headroom.

use anyhow::{Context, Result};
use reqwest::Client;
use std::time::Duration;

use serde_json::Value;

use crate::types::{
    CachedSpec, DriftCheckResult, ForecastColdRequest, ForecastResult, ForecastWarmRequest,
    ParamsRow,
};

pub struct WorkerClient {
    base_url: String,
    http: Client,
}

impl WorkerClient {
    pub fn new(base_url: String) -> Result<Self> {
        let http = Client::builder()
            .timeout(Duration::from_secs(1800))
            .build()
            .context("build reqwest client")?;
        Ok(Self { base_url, http })
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub async fn healthz(&self) -> Result<bool> {
        let url = format!("{}/healthz", self.base_url);
        let r = self.http.get(&url).send().await?;
        Ok(r.status().is_success())
    }

    pub async fn forecast_cold(&self, req: &ForecastColdRequest) -> Result<ForecastResult> {
        let url = format!("{}/forecast/cold", self.base_url);
        let resp = self
            .http
            .post(&url)
            .json(req)
            .send()
            .await
            .context("POST /forecast/cold")?;
        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("/forecast/cold returned {}: {}", status, body);
        }
        let parsed: ForecastResult = resp.json().await.context("parse ForecastResult")?;
        Ok(parsed)
    }

    pub async fn forecast_warm(&self, req: &ForecastWarmRequest) -> Result<ForecastResult> {
        let url = format!("{}/forecast/warm", self.base_url);
        let resp = self.http.post(&url).json(req).send().await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("/forecast/warm returned {}: {}", status, body);
        }
        Ok(resp.json().await?)
    }

    pub async fn drift_check(
        &self,
        sku: &str,
        panel_rows: &[Value],
        params_row: &ParamsRow,
        cached_spec: &CachedSpec,
    ) -> Result<DriftCheckResult> {
        let url = format!("{}/drift/check", self.base_url);
        let body = serde_json::json!({
            "sku": sku,
            "panel_rows": panel_rows,
            "params_row": params_row,
            "cached_spec": cached_spec,
        });
        let resp = self.http.post(&url).json(&body).send().await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            anyhow::bail!("/drift/check returned {}: {}", status, text);
        }
        Ok(resp.json().await?)
    }
}
