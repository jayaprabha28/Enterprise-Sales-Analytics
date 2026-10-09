"""Create the star schema in PostgreSQL and bulk-load cleaned data via COPY."""
import io
import json
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql as pg_sql

from config import DB_HOST, DB_NAME, DB_PORT, DB_USER, PROCESSED_DIR, SQL_DIR

LOAD_DIR = PROCESSED_DIR / "pg_load"
TABLE_ORDER = ["dim_date", "dim_country", "dim_product", "dim_customer", "fact_sales", "fact_returns"]


def ensure_database():
    conn = psycopg2.connect(dbname="postgres", host=DB_HOST, port=DB_PORT, user=DB_USER)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if cur.fetchone() is None:
            cur.execute(pg_sql.SQL("CREATE DATABASE {}").format(pg_sql.Identifier(DB_NAME)))
            print(f"created database {DB_NAME}")
    conn.close()


def _write_csv(df: pd.DataFrame, path: Path):
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
        elif str(out[col].dtype) == "Int64":
            out[col] = out[col].astype(object).where(out[col].notna(), None)
    out.to_csv(path, index=False, header=False)


def build_load_frames():
    dim_date = pd.read_parquet(PROCESSED_DIR / "dim_date.parquet")
    dim_product = pd.read_parquet(PROCESSED_DIR / "dim_product.parquet")
    dim_product.insert(0, "product_key", range(1, len(dim_product) + 1))
    dim_customer = pd.read_parquet(PROCESSED_DIR / "dim_customer.parquet")
    dim_country = pd.read_parquet(PROCESSED_DIR / "dim_country.parquet")
    fact_sales = pd.read_parquet(PROCESSED_DIR / "fact_sales.parquet")
    fact_returns = pd.read_parquet(PROCESSED_DIR / "fact_returns.parquet")

    product_key = dict(zip(dim_product["stockcode"], dim_product["product_key"]))
    customer_key = dict(zip(dim_customer["customer_id"], dim_customer["customer_key"]))
    country_key = dict(zip(dim_country["country"], dim_country["country_key"]))

    for name, fact in (("fact_sales", fact_sales), ("fact_returns", fact_returns)):
        unknown_products = set(fact["stockcode"]) - set(product_key)
        if unknown_products:
            raise ValueError(f"{name} has products missing from dim_product: {unknown_products}")
        fact["product_key"] = fact["stockcode"].map(product_key).astype("int64")
        fact["country_key"] = fact["country"].map(country_key).astype("int64")
        fact["customer_key"] = fact["customer_id"].map(customer_key).astype("Int64")
        fact["date_key"] = fact["date_key"].astype("int64")

    dim_customer["country_key"] = dim_customer["country"].map(country_key).astype("int64")

    dim_country_out = dim_country[["country_key", "country", "region", "country_iso"]]
    dim_customer_out = dim_customer[[
        "customer_key", "customer_id", "country", "region", "country_key", "first_order_date",
        "last_order_date", "orders", "gross_revenue", "refund_amount", "net_revenue",
        "cohort_month", "tenure_days", "country_iso",
    ]]
    sales_out = fact_sales[[
        "line_id", "invoice", "date_key", "customer_key", "product_key", "country_key",
        "quantity", "unit_price", "line_revenue", "is_service",
    ]]
    returns_out = fact_returns[[
        "line_id", "invoice", "date_key", "customer_key", "product_key", "country_key",
        "quantity", "unit_price", "refund_amount",
    ]].rename(columns={"line_id": "return_id"})

    dim_product_out = dim_product[[
        "product_key", "stockcode", "description", "category", "is_service", "typical_price",
        "launch_date", "discontinued_date",
    ]]
    return {
        "dim_date": dim_date,
        "dim_country": dim_country_out,
        "dim_product": dim_product_out,
        "dim_customer": dim_customer_out,
        "fact_sales": sales_out,
        "fact_returns": returns_out,
    }


def run():
    ensure_database()
    frames = build_load_frames()
    LOAD_DIR.mkdir(parents=True, exist_ok=True)
    for name in TABLE_ORDER:
        path = LOAD_DIR / f"{name}.csv"
        _write_csv(frames[name], path)
        print(f"wrote {path.name} ({len(frames[name]):,} rows)")

    conn = psycopg2.connect(dbname=DB_NAME, host=DB_HOST, port=DB_PORT, user=DB_USER)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute((SQL_DIR / "schema.sql").read_text())
        print("schema applied")
        for name in TABLE_ORDER:
            path = LOAD_DIR / f"{name}.csv"
            with open(path, "r", encoding="utf-8") as fh:
                cur.copy_expert(
                    f"COPY {name} FROM STDIN WITH (FORMAT CSV, HEADER FALSE, NULL '')",
                    fh,
                )
            cur.execute(f"SELECT COUNT(*) FROM {name}")
            count = cur.fetchone()[0]
            print(f"loaded {name}: {count:,} rows")
        cur.execute("ANALYZE")
    with conn.cursor() as cur:
        cur.execute("SELECT ROUND(SUM(line_revenue)::numeric, 2) FROM fact_sales")
        gross = cur.fetchone()[0]
        cur.execute("SELECT ROUND(SUM(refund_amount)::numeric, 2) FROM fact_returns")
        refunds = cur.fetchone()[0]
    conn.close()
    kpis = json.loads((PROCESSED_DIR / "kpi_summary.json").read_text())
    summary = {"db": DB_NAME, "fact_sales_revenue": float(gross), "fact_returns_refunds": float(refunds),
               "matches_python": abs(float(gross) - kpis["gross_revenue"]) < 0.01 and abs(float(refunds) - kpis["returns_refunds"]) < 0.01}
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
