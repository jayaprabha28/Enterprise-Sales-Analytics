"""Data quality tests and schema validation for the analytics pipeline."""
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from config import PROCESSED_DIR
from logger import log_data_quality, setup_logging


logger = setup_logging("data_quality")


def validate_schema(df: pd.DataFrame, required_columns: list) -> tuple:
    """Validate DataFrame has required columns."""
    missing = [c for c in required_columns if c not in df.columns]
    return len(missing) == 0, {"missing_columns": missing, "total_columns": len(df.columns)}


def validate_cleaning_report() -> Dict[str, Any]:
    """Validate cleaning report meets expectations."""
    report_path = PROCESSED_DIR / "cleaning_report.json"
    if not report_path.exists():
        return {"status": "FAIL", "message": "cleaning_report.json not found"}

    report = json.loads(report_path.read_text())
    checks = []

    # Reconciliation check
    checks.append(
        ("row_reconciliation", report.get("reconciled") is True, {"reconciled": report.get("reconciled")})
    )

    # Sales + returns + quarantine + dropped should equal raw
    total_accounted = (
        report.get("sales_rows", 0)
        + report.get("return_rows", 0)
        + report.get("quarantined_rows", 0)
        + report.get("dropped_bad_dates", 0)
    )
    checks.append(
        (
            "row_count_balance",
            total_accounted == report.get("raw_rows", -1),
            {"total_accounted": total_accounted, "raw_rows": report.get("raw_rows")},
        )
    )

    # No negative revenues in sales
    checks.append(
        (
            "gross_revenue_positive",
            report.get("gross_sales_revenue", 0) >= 0,
            {"gross_sales_revenue": report.get("gross_sales_revenue")},
        )
    )

    for name, passed, details in checks:
        log_data_quality(name, passed, details, logger)
        if not passed:
            return {"status": "FAIL", "checks": checks}

    return {"status": "PASS", "checks": checks}


def validate_kpi_summary() -> Dict[str, Any]:
    """Validate KPI summary."""
    kpi_path = PROCESSED_DIR / "kpi_summary.json"
    if not kpi_path.exists():
        return {"status": "FAIL", "message": "kpi_summary.json not found"}

    kpi = json.loads(kpi_path.read_text())
    checks = []

    # Key metrics exist and are non-negative where expected
    checks.append(("gross_revenue_exists", "gross_revenue" in kpi, {"gross_revenue": kpi.get("gross_revenue")}))
    checks.append(("net_revenue_exists", "net_revenue" in kpi, {"net_revenue": kpi.get("net_revenue")}))
    checks.append(("orders_positive", kpi.get("orders", 0) > 0, {"orders": kpi.get("orders")}))
    checks.append(("customers_positive", kpi.get("customers_with_id", 0) > 0, {"customers": kpi.get("customers_with_id")}))

    for name, passed, details in checks:
        log_data_quality(name, passed, details, logger)
        if not passed:
            return {"status": "FAIL", "checks": checks}

    return {"status": "PASS", "checks": checks}


def validate_all() -> Dict[str, Any]:
    """Run all data quality validations."""
    results = {
        "cleaning_report": validate_cleaning_report(),
        "kpi_summary": validate_kpi_summary(),
    }
    overall_pass = all(r["status"] == "PASS" for r in results.values())
    return {"status": "PASS" if overall_pass else "FAIL", "results": results}


def run():
    logger.info("Starting data quality validation")
    result = validate_all()
    logger.info(f"Data quality validation completed: {result['status']}")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
