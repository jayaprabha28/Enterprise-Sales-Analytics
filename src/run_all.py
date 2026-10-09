"""Run the entire analytics pipeline end-to-end in dependency order."""
import importlib
import json
import sys
import time
from datetime import datetime

import config
from config import PROCESSED_DIR
from logger import PipelineTimer, setup_logging

STEP_NAMES = [
    "data_cleaning",
    "feature_engineering",
    "load_postgres",
    "run_sql",
    "eda",
    "segmentation",
    "churn_model",
    "forecasting",
    "analytics",
    "recommendation_engine",
    "export_powerbi",
]


def _summary_of(out):
    if not isinstance(out, dict):
        return None
    return {
        k: v for k, v in out.items()
        if k in {"matches_python", "best_k", "silhouette", "best_model", "implied_growth_pct",
                 "gross_revenue", "net_revenue", "realization_pct", "aov", "orders", "customers_segmented",
                 "reports_written", "gross_revenue_matches_kpi"}
    }


def run():
    logger = setup_logging()
    results = {}
    pipeline_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"Starting pipeline run: {pipeline_run_id}")
    for name in STEP_NAMES:
        module = importlib.import_module(name)
        fn = getattr(module, "run", None) or getattr(module, "main", None)
        with PipelineTimer(name, logger):
            print(f"\n{'=' * 70}\n[{name}]\n{'=' * 70}", flush=True)
            try:
                out = fn()
            except Exception as e:
                logger.error(f"Pipeline failed at step: {name}")
                raise
            results[name] = _summary_of(out)
    logger.info(f"Pipeline completed successfully: {pipeline_run_id}")

    print("\n" + "=" * 70 + "\nEND-TO-END VALIDATION\n" + "=" * 70)
    checks = {}
    logger.info("Running end-to-end validation")

    kpi = json.loads((PROCESSED_DIR / "kpi_summary.json").read_text())
    cleaning = json.loads((PROCESSED_DIR / "cleaning_report.json").read_text())
    checks["cleaned_rows_reconciled"] = cleaning.get("reconciled")
    checks["gross_revenue"] = kpi.get("gross_revenue")
    checks["net_revenue"] = kpi.get("net_revenue")
    checks["orders"] = kpi.get("orders")
    checks["customers"] = kpi.get("customers_with_id")
    checks["churn_rate_pct"] = kpi.get("churn_rate_pct")
    checks["postgres_matches_python"] = results.get("load_postgres", {}).get("matches_python")

    for name in ("kpi_summary.json", "eda_summary.json", "segmentation_summary.json",
                 "churn_model_summary.json", "forecast_summary.json", "analytics_summary.json"):
        checks[f"exists:{name}"] = (PROCESSED_DIR / name).exists()
    checks["exists:business_insights"] = config.REPORTS_DIR.joinpath("business_insights.md").exists()
    checks["exists:recommendations"] = config.REPORTS_DIR.joinpath("recommendations.md").exists()
    checks["powerbi_csv_count"] = len(list(config.POWERBI_DATA_DIR.glob("*.csv")))
    checks["sql_result_count"] = len(list(config.SQL_RESULTS_DIR.glob("*.csv")))
    checks["figure_count"] = len(list(config.FIGURES_DIR.glob("*.png")))

    print(json.dumps(checks, indent=2))
    logger.info(f"Validation complete: {checks}")
    return checks


if __name__ == "__main__":
    run()