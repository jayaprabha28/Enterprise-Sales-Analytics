"""Clean the raw Online Retail II extract into analytics-ready fact tables."""
import json

import numpy as np
import pandas as pd

from config import COUNTRY_ISO_MAP, COUNTRY_REGION_MAP, PROCESSED_DIR, RAW_CSV, SERVICE_CODES


def load_raw(path=RAW_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df.rename(columns={
        "Invoice": "invoice",
        "StockCode": "stockcode",
        "Description": "description",
        "Quantity": "quantity",
        "InvoiceDate": "invoice_date",
        "Price": "unit_price",
        "Customer ID": "customer_id",
        "Country": "country",
    })
    for col in ("invoice", "stockcode", "description", "country"):
        df[col] = df[col].astype("string").str.strip()
    df["invoice"] = df["invoice"].str.upper()
    df["stockcode"] = df["stockcode"].str.upper()
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df["customer_id"] = pd.to_numeric(df["customer_id"], errors="coerce").astype("Int64")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    return df


def _quarantine(df, mask, reason, log):
    removed = df.loc[mask].copy()
    removed["quarantine_reason"] = reason
    log.append(removed)
    return df.loc[~mask].copy()


def _classify_rows(df):
    is_gift_voucher = df["stockcode"].str.startswith("GIFT_", na=False)
    df["is_service"] = df["stockcode"].isin(SERVICE_CODES) | is_gift_voucher
    return df


def clean(df=None):
    if df is None:
        df = load_raw()
    quarantine_log = []
    report = {"raw_rows": int(len(df))}

    df = df[df["invoice_date"].notna()]
    report["dropped_bad_dates"] = report["raw_rows"] - int(len(df))

    df = _quarantine(df, df.duplicated(keep="first"), "duplicate_row", quarantine_log)
    df = _quarantine(df, df["quantity"].isna() | df["unit_price"].isna(), "null_measure", quarantine_log)
    df = _quarantine(df, df["unit_price"] < 0, "negative_price", quarantine_log)
    df = _quarantine(df, df["quantity"] == 0, "zero_quantity", quarantine_log)

    df = _classify_rows(df)
    mode_by_code = df.groupby("stockcode")["description"].transform(lambda s: s.mode().iloc[0] if not s.mode().empty else pd.NA)
    df["description"] = df["description"].fillna(mode_by_code).fillna("UNKNOWN")

    df["country"] = df["country"].fillna("Unspecified").replace({"": "Unspecified"})
    df["region"] = df["country"].map(COUNTRY_REGION_MAP).fillna("Unknown")
    df["country_iso"] = df["country"].map(COUNTRY_ISO_MAP).fillna(df["country"].str[:2].str.upper())

    df["is_credit_note"] = df["invoice"].str.startswith("C", na=False)
    df["line_revenue"] = (df["quantity"] * df["unit_price"]).round(2)
    df["date_key"] = df["invoice_date"].dt.strftime("%Y%m%d").astype(int)
    df["line_id"] = np.arange(1, len(df) + 1, dtype=np.int64)

    returns_mask = df["is_credit_note"] | (df["quantity"] < 0)
    fact_returns = df.loc[returns_mask].copy()
    fact_sales = df.loc[~returns_mask].copy()

    fact_returns["refund_amount"] = (-(fact_returns["quantity"] * fact_returns["unit_price"])).round(2)
    fact_sales = fact_sales[fact_sales["quantity"] > 0].copy()

    quarantine = (
        pd.concat(quarantine_log, ignore_index=True)
        if quarantine_log
        else pd.DataFrame(columns=list(df.columns) + ["quarantine_reason"])
    )

    report.update({
        "quarantined_rows": int(len(quarantine)),
        "quarantine_reasons": quarantine["quarantine_reason"].value_counts().to_dict() if len(quarantine) else {},
        "sales_rows": int(len(fact_sales)),
        "return_rows": int(len(fact_returns)),
        "reconciled": int(len(fact_sales) + len(fact_returns) + len(quarantine) + report["dropped_bad_dates"]) == report["raw_rows"],
        "gross_sales_revenue": round(float(fact_sales["line_revenue"].sum()), 2),
        "returns_refunds": round(float(fact_returns["refund_amount"].sum()), 2),
        "net_revenue": round(float(fact_sales["line_revenue"].sum() - fact_returns["refund_amount"].sum()), 2),
        "null_customer_id_rows": int(fact_sales["customer_id"].isna().sum()),
        "date_min": str(fact_sales["invoice_date"].min()),
        "date_max": str(fact_sales["invoice_date"].max()),
        "distinct_invoices": int(fact_sales["invoice"].nunique()),
        "distinct_customers": int(fact_sales["customer_id"].nunique()),
        "distinct_products": int(fact_sales["stockcode"].nunique()),
    })

    sales_cols = ["line_id", "invoice", "invoice_date", "date_key", "stockcode", "description",
                  "customer_id", "country", "region", "country_iso", "quantity", "unit_price",
                  "line_revenue", "is_service", "is_credit_note"]
    return_cols = ["line_id", "invoice", "invoice_date", "date_key", "stockcode", "description",
                   "customer_id", "country", "region", "quantity", "unit_price", "refund_amount",
                   "is_credit_note"]
    return fact_sales[sales_cols].reset_index(drop=True), fact_returns[return_cols].reset_index(drop=True), quarantine, report


def write_outputs(fact_sales, fact_returns, quarantine, report):
    fact_sales.to_parquet(PROCESSED_DIR / "fact_sales.parquet", index=False)
    fact_returns.to_parquet(PROCESSED_DIR / "fact_returns.parquet", index=False)
    quarantine.to_parquet(PROCESSED_DIR / "quarantine.parquet", index=False)
    with open(PROCESSED_DIR / "cleaning_report.json", "w") as fh:
        json.dump(report, fh, indent=2, default=str)


def run():
    fact_sales, fact_returns, quarantine, report = clean()
    write_outputs(fact_sales, fact_returns, quarantine, report)
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
