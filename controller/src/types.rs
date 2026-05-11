//! Serde types mirroring the Python worker's Pydantic schemas.
//! Keep field names and types in sync with services/worker/schemas/{requests,responses}.py.

#![allow(dead_code)] // Fields are serialized/deserialized but not always accessed in Rust.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use time::Date;

// ------------------------------- Request types -------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PanelRow {
    #[serde(with = "time::serde::iso8601")]
    pub ds: time::OffsetDateTime,
    pub y: f64,
    pub orders: f64,
    pub stock: f64,
}

/// Same shape as PanelRow but with a plain Date — used when we read straight from Postgres.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PanelRowDate {
    pub ds: Date,
    pub y: f64,
    pub orders: f64,
    pub stock: f64,
}

impl PanelRowDate {
    pub fn to_iso_row(&self) -> serde_json::Value {
        let ds_str = self
            .ds
            .format(&time::format_description::well_known::Iso8601::DATE)
            .expect("format date");
        serde_json::json!({
            "ds": ds_str,
            "y": self.y,
            "orders": self.orders,
            "stock": self.stock,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamsRow {
    pub t_check: i32,
    pub h_cover: i32,
    pub q_target: f64,
    #[serde(default)]
    pub lead_time_mo: i32,
    #[serde(default)]
    pub moq: f64,
    #[serde(default = "default_lot_size")]
    pub lot_size: f64,
    #[serde(default)]
    pub starting_stock_override: Option<f64>,
}

fn default_lot_size() -> f64 { 1.0 }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedModelRef {
    pub model_slot: String,
    pub column_target: String,
    pub hyperparams: Value,
    pub blob_uri: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedExogSelection {
    pub column_target: String,
    pub chosen_method: String,
    pub val_mae: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedValResidual {
    pub exog: String,
    pub y_variant: String,
    pub residuals: Vec<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedSpec {
    pub prior_run_id: i64,
    pub winning_horizon: String,
    pub winning_exog: String,
    pub winning_y_variant: String,
    pub winning_phase: String,
    pub winning_w_rf: Option<f64>,
    pub winning_w_xgb: Option<f64>,
    pub models: Vec<CachedModelRef>,
    pub exog_selection: Vec<CachedExogSelection>,
    pub val_residuals: Vec<CachedValResidual>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ForecastColdRequest {
    pub sku: String,
    pub run_id: i64,
    pub panel_rows: Vec<serde_json::Value>,
    pub params_row: ParamsRow,
    pub blob_dir: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ForecastWarmRequest {
    pub sku: String,
    pub run_id: i64,
    pub panel_rows: Vec<serde_json::Value>,
    pub params_row: ParamsRow,
    pub blob_dir: String,
    pub cached_spec: CachedSpec,
}

// ------------------------------- Response types -------------------------------

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct WinningCombo {
    pub horizon: String,
    pub exog: String,
    pub y_variant: String,
    pub phase: String,
    pub mae: f64,
    pub rmse: f64,
    pub mape: Option<f64>,
    pub w_rf: Option<f64>,
    pub w_xgb: Option<f64>,
    pub p_stockout_3m: Option<f64>,
    pub p_stockout_6m: Option<f64>,
    pub e_t_stockout_mo: Option<f64>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CombinationRow {
    pub horizon: String,
    pub exog: String,
    pub y_variant: String,
    pub phase: String,
    pub mae: f64,
    pub rmse: Option<f64>,
    pub mape: Option<f64>,
    pub w_rf: Option<f64>,
    pub w_xgb: Option<f64>,
    pub p_stockout_3m: Option<f64>,
    pub p_stockout_6m: Option<f64>,
    pub e_t_stockout_mo: Option<f64>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ModelRow {
    pub model_slot: String,
    pub column_target: String,
    pub hyperparams: Value,
    pub blob_uri: String,
    pub fit_seconds: f64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ExogSelectionRow {
    pub column_target: String,
    pub chosen_method: String,
    pub val_mae: f64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ValResidualRow {
    pub exog: String,
    pub y_variant: String,
    pub residuals: Vec<f64>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PredictionRow {
    pub ds: String,
    pub y: Option<f64>,
    pub yhat: f64,
    pub pi80_lo: Option<f64>,
    pub pi80_hi: Option<f64>,
    pub pi95_lo: Option<f64>,
    pub pi95_hi: Option<f64>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RecommendationRow {
    pub starting_stock: f64,
    pub t_check: i32,
    pub h_cover: i32,
    pub q_target: f64,
    pub moq: f64,
    pub lot_size: f64,
    pub cum_demand_q: f64,
    pub order_qty_raw: f64,
    pub order_qty_rounded: f64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ForecastResult {
    pub sku: String,
    pub run_id: i64,
    pub mode: String,
    pub winning: WinningCombo,
    #[serde(default)]
    pub combinations: Vec<CombinationRow>,
    #[serde(default)]
    pub models: Vec<ModelRow>,
    #[serde(default)]
    pub exog_selection: Vec<ExogSelectionRow>,
    #[serde(default)]
    pub val_residuals: Vec<ValResidualRow>,
    #[serde(default)]
    pub predictions: Vec<PredictionRow>,
    pub recommendation: RecommendationRow,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct DriftCheckResult {
    pub drift_triggered: bool,
    pub new_mae: f64,
    pub cached_mae: f64,
    pub threshold: f64,
}
