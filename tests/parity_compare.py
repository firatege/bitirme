"""Parity-compare the services/worker output (DB) against scripts/model_v3.py output (CSVs).

Run after:
    1) A full-panel API run has populated sku_runs in Postgres (via docker compose).
    2) `python scripts/model_v3.py` has run locally and written outputs/{SKU}/test_summary_ALL.csv.

Prints, per SKU:
    - winning combo from DB         (api_exog, api_variant, api_phase, api_mae)
    - winning combo from CSV        (script_exog, script_variant, script_phase, script_mae)
    - mae delta                     (api - script; positive = service is worse)

At the bottom, aggregate stats: combo-match rate, mean/median MAE delta.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pandas as pd


REPO = Path(__file__).resolve().parent.parent
OUTPUTS = REPO / "outputs"


def api_winners() -> pd.DataFrame:
    """Pull the latest sku_runs row per SKU from Postgres."""
    sql = """
        SELECT DISTINCT ON (sku)
            sku,
            winning_horizon::text AS horizon,
            winning_exog          AS exog,
            winning_y_variant::text AS y_variant,
            winning_phase::text   AS phase,
            winning_mae           AS mae
        FROM sku_runs
        WHERE status = 'completed'
        ORDER BY sku, completed_at DESC NULLS LAST, run_id DESC
    """
    out = subprocess.check_output(
        [
            "docker", "compose", "exec", "-T", "postgres",
            "psql", "-U", "bitirme", "-d", "bitirme",
            "-F", "\t", "-A", "-c", sql,
        ],
        cwd=REPO, text=True,
    )
    # Strip header + trailing "(N rows)" line.
    lines = [l for l in out.strip().splitlines() if l and not l.startswith("(")]
    header = lines[0].split("\t")
    rows = [dict(zip(header, l.split("\t"))) for l in lines[1:]]
    for r in rows:
        r["mae"] = float(r["mae"]) if r["mae"] else float("nan")
    return pd.DataFrame(rows)


def script_winner(sku: str) -> Optional[dict]:
    """Best (Horizon='Full') row from outputs/{SKU}/test_summary_ALL.csv."""
    p = OUTPUTS / sku / "test_summary_ALL.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if "Horizon" in df.columns:
        df = df[df["Horizon"] == "Full"]
    if df.empty:
        return None
    # Also merge in REFIT if present
    p_refit = OUTPUTS / sku / "test_summary_ALL_REFIT.csv"
    if p_refit.exists():
        df_r = pd.read_csv(p_refit)
        if "Horizon" in df_r.columns:
            df_r = df_r[df_r["Horizon"] == "Full"]
        df_r["Phase"] = "REFIT"
        df["Phase"] = "PRE"
        df = pd.concat([df, df_r], ignore_index=True)
    row = df.sort_values("MAE").iloc[0]
    return {
        "horizon": str(row.get("Horizon", "Full")),
        "exog":    str(row["Exog"]),
        "y_variant": str(row["Y-Variant"]),
        "phase":   str(row.get("Phase", "PRE")),
        "mae":     float(row["MAE"]),
    }


def main() -> int:
    api = api_winners()
    if api.empty:
        print("no API winners in DB — did you run `controller monthly-run`?", file=sys.stderr)
        return 1

    rows = []
    for _, a in api.iterrows():
        sku = a["sku"]
        s = script_winner(sku)
        if s is None:
            rows.append({
                "sku": sku,
                "api_exog": a["exog"], "api_variant": a["y_variant"], "api_phase": a["phase"], "api_mae": a["mae"],
                "script_exog": None,   "script_variant": None,         "script_phase": None,    "script_mae": None,
                "combo_match": None,   "mae_delta": None,
            })
            continue
        combo_match = (a["exog"] == s["exog"]) and (a["y_variant"] == s["y_variant"]) and (a["phase"] == s["phase"])
        rows.append({
            "sku": sku,
            "api_exog": a["exog"], "api_variant": a["y_variant"], "api_phase": a["phase"], "api_mae": a["mae"],
            "script_exog": s["exog"], "script_variant": s["y_variant"], "script_phase": s["phase"], "script_mae": s["mae"],
            "combo_match": combo_match,
            "mae_delta":   a["mae"] - s["mae"],
        })

    df = pd.DataFrame(rows)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_colwidth", 40)
    pd.set_option("display.width", 240)
    print(df.to_string(index=False))
    print()

    compared = df.dropna(subset=["script_mae"])
    if not compared.empty:
        print(f"SKUs compared: {len(compared)} / {len(df)}")
        print(f"combo match rate: {compared['combo_match'].mean() * 100:.1f}%")
        print(f"mae_delta mean:   {compared['mae_delta'].mean():+.3f}")
        print(f"mae_delta median: {compared['mae_delta'].median():+.3f}")
        print(f"api MAE mean:     {compared['api_mae'].mean():.3f}")
        print(f"script MAE mean:  {compared['script_mae'].mean():.3f}")

    out_csv = REPO / "tests" / "parity.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nwrote {out_csv.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
