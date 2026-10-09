"""Export star schema + flat report tables as CSVs for Power BI Desktop.

Outputs (see powerbi/README.md):
  data/processed/powerbi/*.csv — 6 star tables + 7 flat report tables
"""
import json

import pandas as pd

from config import PROCESSED_DIR
from load_postgres import build_load_frames

POWERBI_DIR = PROCESSED_DIR / "powerbi"

CUSTOMER_INSIGHT_COLUMNS = [
    "customer_id", "customer_key", "country", "region", "recency_days", "frequency",
    "monetary", "avg_order_value", "r_score", "f_score", "m_score", "rfm_segment",
    "kmeans_segment", "churn_probability", "risk_level", "churned_actual",
    "tenure_days", "return_rate", "distinct_products",
]
FORECAST_COLUMNS = [
    "forecast_month", "model", "forecast_net_revenue", "lower_95", "upper_95", "actual_net_revenue",
]
MODEL_METRIC_COLUMNS = ["model", "auc", "accuracy", "precision", "recall", "f1"]
MONTHLY_COLUMNS = [
    "year_month", "gross_revenue", "orders", "units", "lines", "active_customers",
    "refunds", "net_revenue", "new_customers", "returning_customers", "aov",
]
PRODUCT_COLUMNS = [
    "stockcode", "description", "category", "units_sold", "gross_revenue", "net_revenue",
    "orders", "customers", "return_rate", "growth_90d_pct", "abc_class", "days_since_last_sale",
]
INVENTORY_COLUMNS = [
    "stockcode", "description", "category", "units_sold", "orders", "last_sale",
    "days_since_last_sale", "stockout_weeks_52w", "avg_weekly_units", "reorder_point_units",
    "movement_class",
]


def _format_csv(out: pd.DataFrame) -> pd.DataFrame:
    out = out.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
        elif str(out[col].dtype) == "Int64":
            out[col] = out[col].astype(object).where(out[col].notna(), None)
    return out


def _write(df: pd.DataFrame, name: str) -> int:
    _format_csv(df).to_csv(POWERBI_DIR / name, index=False)
    print(f"wrote {name} ({len(df):,} rows)")
    return len(df)


def build_flat_frames():
    segments = pd.read_parquet(PROCESSED_DIR / "customer_segments.parquet")
    churn = pd.read_csv(PROCESSED_DIR / "churn_predictions.csv")[
        ["customer_id", "churn_probability", "risk_level", "churned_actual"]
    ]
    dim_customer = pd.read_parquet(PROCESSED_DIR / "dim_customer.parquet")[["customer_key", "customer_id"]]
    customer_insights = (
        segments.merge(churn, on="customer_id", how="left")
        .merge(dim_customer, on="customer_id", how="left")
    )
    freq = customer_insights["frequency"].where(customer_insights["frequency"] > 0)
    customer_insights["avg_order_value"] = (customer_insights["monetary"] / freq).round(2)
    customer_insights = customer_insights[CUSTOMER_INSIGHT_COLUMNS]

    cohort = pd.read_parquet(PROCESSED_DIR / "cohort_retention.parquet")
    month_cols = [c for c in cohort.columns if c.isdigit() and int(c) <= 12]
    cohort = cohort[["cohort_month"] + month_cols]

    forecast = pd.read_csv(PROCESSED_DIR / "forecast_monthly.csv")[FORECAST_COLUMNS]
    model_metrics = pd.read_csv(PROCESSED_DIR / "model_metrics.csv")[MODEL_METRIC_COLUMNS]
    monthly = pd.read_parquet(PROCESSED_DIR / "monthly_series.parquet")[MONTHLY_COLUMNS]
    products = pd.read_parquet(PROCESSED_DIR / "product_features.parquet")[PRODUCT_COLUMNS]
    inventory = pd.read_parquet(PROCESSED_DIR / "inventory_features.parquet")[INVENTORY_COLUMNS]

    return {
        "customer_insights.csv": customer_insights,
        "forecast_monthly.csv": forecast,
        "model_metrics.csv": model_metrics,
        "monthly_series.csv": monthly,
        "cohort_retention.csv": cohort,
        "product_features.csv": products,
        "inventory_features.csv": inventory,
    }


def run():
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}

    for name, frame in build_load_frames().items():
        summary[name.replace(".parquet", "")] = _write(frame, f"{name}.csv")
    for name, frame in build_flat_frames().items():
        summary[name.replace(".csv", "")] = _write(frame, name)

    kpis = json.loads((PROCESSED_DIR / "kpi_summary.json").read_text())
    fact_sales = pd.read_csv(POWERBI_DIR / "fact_sales.csv", dtype={"invoice": "string"}, low_memory=False)
    gross = round(float(fact_sales["line_revenue"].sum()), 2)
    checks = {
        "rows_fact_sales": int(summary["fact_sales"]),
        "rows_fact_returns": int(summary["fact_returns"]),
        "rows_customer_insights": int(summary["customer_insights"]),
        "gross_revenue_matches_kpi": abs(gross - kpis["gross_revenue"]) < 0.01,
    }
    print(json.dumps(checks, indent=2))
    if not checks["gross_revenue_matches_kpi"]:
        raise ValueError(f"fact_sales revenue {gross} != kpi {kpis['gross_revenue']}")
    (POWERBI_DIR / "export_summary.json").write_text(json.dumps({"rows": summary, "checks": checks}, indent=2))
    return summary


if __name__ == "__main__":
    run()
