//! Types-layer tests — serde roundtrip for the Python ↔ Rust wire contract. No DB.

use controller::types::{CachedSpec, ForecastResult};

#[test]
fn forecast_result_parses_known_payload() {
    let json = r#"
    {
      "sku": "303-104092",
      "run_id": 42,
      "mode": "cold",
      "winning": {
        "horizon": "Full",
        "exog": "Hybrid[o=ETS,s=ML-Exog RF]",
        "y_variant": "Y-ENS",
        "phase": "PRE",
        "mae": 12.3, "rmse": 15.1,
        "mape": null, "w_rf": 0.58, "w_xgb": 0.42,
        "p_stockout_3m": 0.02, "p_stockout_6m": 0.09, "e_t_stockout_mo": 5.1
      },
      "combinations": [],
      "models": [],
      "exog_selection": [],
      "val_residuals": [],
      "recommendation": {
        "starting_stock": 120.0, "t_check": 3, "h_cover": 6, "q_target": 0.5,
        "moq": 0.0, "lot_size": 1.0, "cum_demand_q": 85.4,
        "order_qty_raw": -34.6, "order_qty_rounded": 0.0
      }
    }
    "#;
    let parsed: ForecastResult = serde_json::from_str(json).expect("parse ForecastResult");
    assert_eq!(parsed.sku, "303-104092");
    assert_eq!(parsed.run_id, 42);
    assert_eq!(parsed.winning.y_variant, "Y-ENS");
    assert_eq!(parsed.winning.mae, 12.3);
    assert_eq!(parsed.recommendation.cum_demand_q, 85.4);
}

#[test]
fn cached_spec_roundtrip() {
    let spec = CachedSpec {
        prior_run_id: 1,
        winning_horizon: "Full".into(),
        winning_exog: "ETS".into(),
        winning_y_variant: "Y-ENS".into(),
        winning_phase: "PRE".into(),
        winning_w_rf: Some(0.5),
        winning_w_xgb: Some(0.5),
        models: vec![],
        exog_selection: vec![],
        val_residuals: vec![],
    };
    let j = serde_json::to_string(&spec).unwrap();
    let back: CachedSpec = serde_json::from_str(&j).unwrap();
    assert_eq!(back.prior_run_id, 1);
    assert_eq!(back.winning_horizon, "Full");
}

#[test]
fn default_lot_size_is_one() {
    use controller::types::ParamsRow;
    let json = r#"{"t_check": 3, "h_cover": 6, "q_target": 0.5}"#;
    let p: ParamsRow = serde_json::from_str(json).unwrap();
    assert_eq!(p.lot_size, 1.0);
    assert_eq!(p.moq, 0.0);
    assert_eq!(p.lead_time_mo, 0);
    assert!(p.starting_stock_override.is_none());
}
