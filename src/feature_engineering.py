"""Build dimensional tables, customer/product features and time series from cleaned facts."""
import json

import numpy as np
import pandas as pd

from config import CATEGORY_RULES, CHURN_INACTIVITY_DAYS, PROCESSED_DIR, SERVICE_CATEGORY_RULES, SERVICE_CODES


def load_facts():
    sales = pd.read_parquet(PROCESSED_DIR / "fact_sales.parquet")
    returns = pd.read_parquet(PROCESSED_DIR / "fact_returns.parquet")
    sales["invoice_date"] = pd.to_datetime(sales["invoice_date"])
    returns["invoice_date"] = pd.to_datetime(returns["invoice_date"])
    return sales, returns


def build_dim_date(sales):
    days = pd.date_range(sales["invoice_date"].min().normalize(), sales["invoice_date"].max().normalize(), freq="D")
    dim = pd.DataFrame({"date_key": days.strftime("%Y%m%d").astype(int), "full_date": days})
    dim["year"] = days.year
    dim["quarter"] = days.quarter
    dim["month"] = days.month
    dim["month_name"] = days.strftime("%b")
    dim["year_month"] = days.strftime("%Y-%m")
    dim["iso_week"] = days.isocalendar().week.astype(int).values
    dim["year_week"] = days.strftime("%Y-W%V")
    dim["day_of_week"] = days.dayofweek + 1
    dim["day_name"] = days.strftime("%a")
    dim["is_weekend"] = days.dayofweek >= 5
    dim["is_month_start"] = days.is_month_start
    dim["is_month_end"] = days.is_month_end
    dim["week_starting"] = (days - pd.to_timedelta(days.dayofweek, unit="D"))
    return dim


def categorize(description, is_service, stockcode):
    if is_service:
        return SERVICE_CATEGORY_RULES.get(stockcode, "Other Services")
    text = str(description).upper()
    for category, keywords in CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return category
    return "Other Products"


def build_dim_product(sales, returns):
    returns = returns.copy()
    returns["is_service"] = returns["stockcode"].isin(SERVICE_CODES) | returns["stockcode"].str.startswith("GIFT_", na=False)
    returns["line_revenue"] = returns["quantity"] * returns["unit_price"]
    all_lines = pd.concat([
        sales[["stockcode", "description", "quantity", "unit_price", "is_service", "invoice_date"]],
        returns[["stockcode", "description", "quantity", "unit_price", "is_service", "invoice_date"]],
    ], ignore_index=True)
    desc_mode = all_lines.groupby("stockcode")["description"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "UNKNOWN")
    is_service_map = all_lines.groupby("stockcode")["is_service"].max()
    typical_price = (
        all_lines[(all_lines["quantity"] > 0) & (~all_lines["is_service"])]
        .groupby("stockcode")["unit_price"].median().round(2)
    )
    dim = pd.DataFrame({"stockcode": desc_mode.index})
    dim["description"] = desc_mode.values
    dim["is_service"] = is_service_map.reindex(dim["stockcode"]).fillna(False).values
    dim["category"] = [
        categorize(row.description, row.is_service, row.stockcode)
        for row in dim.itertuples()
    ]
    dim["typical_price"] = typical_price.reindex(dim["stockcode"]).values
    dim["launch_date"] = all_lines.groupby("stockcode")["invoice_date"].min().reindex(dim["stockcode"]).values
    dim["discontinued_date"] = all_lines.groupby("stockcode")["invoice_date"].max().reindex(dim["stockcode"]).values
    return dim


def build_dim_customer(sales, returns, snapshot):
    customer_sales = sales[sales["customer_id"].notna()]
    customer_returns = returns[returns["customer_id"].notna()]
    grouped = customer_sales.groupby("customer_id")
    dim = pd.DataFrame({
        "customer_id": grouped.size().index,
        "country": grouped["country"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "Unknown").values,
        "region": grouped["region"].agg(lambda s: s.mode().iloc[0]).values,
        "first_order_date": grouped["invoice_date"].min().values,
        "last_order_date": grouped["invoice_date"].max().values,
        "orders": grouped["invoice"].nunique().values,
        "gross_revenue": grouped["line_revenue"].sum().values,
    })
    refunds = customer_returns.groupby("customer_id")["refund_amount"].sum()
    dim["refund_amount"] = dim["customer_id"].map(refunds).fillna(0.0)
    dim["net_revenue"] = dim["gross_revenue"] - dim["refund_amount"]
    dim["cohort_month"] = pd.to_datetime(dim["first_order_date"]).dt.strftime("%Y-%m")
    dim["tenure_days"] = (snapshot - pd.to_datetime(dim["first_order_date"]).dt.normalize()).dt.days
    dim["country_iso"] = dim["country"].str[:2].str.upper()
    dim = dim.sort_values("customer_id").reset_index(drop=True)
    dim.insert(0, "customer_key", np.arange(1, len(dim) + 1, dtype=np.int64))
    return dim


def build_dim_country(sales):
    dim = sales.groupby(["country", "region", "country_iso"], as_index=False).agg(
        gross_revenue=("line_revenue", "sum"),
        orders=("invoice", "nunique"),
        customers=("customer_id", "nunique"),
    )
    dim = dim.sort_values("gross_revenue", ascending=False).reset_index(drop=True)
    dim.insert(0, "country_key", np.arange(1, len(dim) + 1, dtype=np.int64))
    return dim


def build_customer_features(sales, returns, dim_customer, dim_product, snapshot):
    known = sales[sales["customer_id"].notna()].copy()
    known_returns = returns[returns["customer_id"].notna()].copy()

    typical = dim_product.set_index("stockcode")["typical_price"]
    known["typical_price"] = known["stockcode"].map(typical)
    known["price_vs_typical"] = np.where(
        known["typical_price"].notna() & (known["typical_price"] > 0),
        1 - known["unit_price"] / known["typical_price"],
        0.0,
    )

    grouped = known.groupby("customer_id")
    features = pd.DataFrame({
        "customer_id": grouped.size().index,
        "recency_days": (snapshot - grouped["invoice_date"].max().dt.normalize()).dt.days.values,
        "frequency": grouped["invoice"].nunique().values,
        "monetary": grouped["line_revenue"].sum().values,
        "total_units": grouped["quantity"].sum().values,
        "distinct_products": grouped["stockcode"].nunique().values,
        "purchase_days": grouped["invoice_date"].apply(lambda s: s.dt.normalize().nunique()).values,
        "avg_discount_pct": grouped["price_vs_typical"].mean().values,
        "tenure_days": (snapshot - grouped["invoice_date"].min().dt.normalize()).dt.days.values,
        "avg_price_paid": grouped["unit_price"].mean().values,
    })
    invoice_level = known.groupby(["customer_id", "invoice"]).agg(
        units=("quantity", "sum"),
        lines=("line_id", "count"),
        day=("invoice_date", "first"),
    ).reset_index()
    order_totals = invoice_level.groupby("customer_id")["units"].sum()
    features["avg_units_per_order"] = (features["customer_id"].map(order_totals) / features["frequency"]).round(1)
    first_gap = invoice_level.sort_values(["customer_id", "day"]).groupby("customer_id")["day"].diff().dt.days
    invoice_level["gap"] = first_gap
    avg_gap = invoice_level.groupby("customer_id")["gap"].mean()
    features["avg_purchase_gap_days"] = features["customer_id"].map(avg_gap).round(1)
    features["avg_purchase_gap_days"] = features["avg_purchase_gap_days"].fillna(
        features["avg_purchase_gap_days"].median()
    )
    features["orders_per_month"] = (features["frequency"] / (features["tenure_days"].clip(lower=1) / 30.44)).round(2)
    weekend_share = known.groupby("customer_id")["invoice_date"].apply(lambda s: (s.dt.dayofweek >= 5).mean())
    features["weekend_order_share"] = features["customer_id"].map(weekend_share).round(3)

    if len(known_returns):
        ret = known_returns.groupby("customer_id").agg(
            return_lines=("line_id", "count"),
            refund_amount=("refund_amount", "sum"),
        )
        features["return_lines"] = features["customer_id"].map(ret["return_lines"]).fillna(0).astype(int)
        features["refund_amount"] = features["customer_id"].map(ret["refund_amount"]).fillna(0.0)
    else:
        features["return_lines"] = 0
        features["refund_amount"] = 0.0

    features["return_rate"] = (features["return_lines"] / (features["return_lines"] + features["frequency"])).round(4)
    features["monetary"] = features["monetary"] - features["refund_amount"]
    features = features.merge(dim_customer[["customer_id", "country", "region"]], on="customer_id", how="left")
    features["churned"] = (features["recency_days"] > CHURN_INACTIVITY_DAYS).astype(int)
    return features


def build_product_features(sales, returns, dim_product, snapshot):
    grouped = sales.groupby("stockcode")
    features = pd.DataFrame({
        "stockcode": grouped.size().index,
        "units_sold": grouped["quantity"].sum().values,
        "gross_revenue": grouped["line_revenue"].sum().values,
        "orders": grouped["invoice"].nunique().values,
        "customers": grouped["customer_id"].nunique().values,
        "avg_price": grouped["unit_price"].mean().values,
        "first_sale": grouped["invoice_date"].min().values,
        "last_sale": grouped["invoice_date"].max().values,
    })
    if len(returns):
        ret = returns.groupby("stockcode").agg(return_units=("quantity", lambda s: s.abs().sum()), refund_amount=("refund_amount", "sum"))
        features["return_units"] = features["stockcode"].map(ret["return_units"]).fillna(0)
        features["refund_amount"] = features["stockcode"].map(ret["refund_amount"]).fillna(0.0)
    else:
        features["return_units"] = 0.0
        features["refund_amount"] = 0.0
    features["net_revenue"] = features["gross_revenue"] - features["refund_amount"]
    features["return_rate"] = (features["return_units"] / features["units_sold"].clip(lower=1)).round(4)

    last_90 = snapshot - pd.Timedelta(days=90)
    prior_90 = snapshot - pd.Timedelta(days=180)
    rev_recent = sales[sales["invoice_date"] > last_90].groupby("stockcode")["line_revenue"].sum()
    rev_prior = sales[(sales["invoice_date"] > prior_90) & (sales["invoice_date"] <= last_90)].groupby("stockcode")["line_revenue"].sum()
    features["revenue_last_90d"] = features["stockcode"].map(rev_recent).fillna(0.0)
    prior = features["stockcode"].map(rev_prior).fillna(0.0)
    features["revenue_prior_90d"] = prior
    features["growth_90d_pct"] = np.where(prior > 0, ((features["revenue_last_90d"] - prior) / prior * 100).round(1), np.nan)
    features["days_since_last_sale"] = (snapshot - pd.to_datetime(features["last_sale"]).dt.normalize()).dt.days
    features = features.merge(dim_product[["stockcode", "description", "category", "is_service", "typical_price"]], on="stockcode", how="left")
    features = features.sort_values("net_revenue", ascending=False).reset_index(drop=True)
    features["abc_class"] = np.where(
        features["net_revenue"].cumsum() / features["net_revenue"].sum() <= 0.8, "A",
        np.where(features["net_revenue"].cumsum() / features["net_revenue"].sum() <= 0.95, "B", "C"),
    )
    return features


def build_time_series(sales, returns):
    sales = sales.copy()
    returns = returns.copy()
    sales["year_month"] = sales["invoice_date"].dt.strftime("%Y-%m")
    returns["year_month"] = returns["invoice_date"].dt.strftime("%Y-%m")
    monthly = sales.groupby("year_month").agg(
        gross_revenue=("line_revenue", "sum"),
        orders=("invoice", "nunique"),
        units=("quantity", "sum"),
        lines=("line_id", "count"),
        active_customers=("customer_id", "nunique"),
    )
    refunds = returns.groupby("year_month")["refund_amount"].sum()
    monthly["refunds"] = refunds.reindex(monthly.index).fillna(0.0)
    monthly["net_revenue"] = monthly["gross_revenue"] - monthly["refunds"]
    first_purchase = sales.groupby("customer_id")["invoice_date"].min().dt.strftime("%Y-%m")
    new_by_month = first_purchase.value_counts()
    monthly["new_customers"] = new_by_month.reindex(monthly.index).fillna(0).astype(int)
    monthly["returning_customers"] = monthly["active_customers"] - monthly["new_customers"]
    monthly["aov"] = (monthly["net_revenue"] / monthly["orders"]).round(2)
    monthly = monthly.reset_index()

    sales["week_starting"] = sales["invoice_date"].dt.normalize() - pd.to_timedelta(sales["invoice_date"].dt.dayofweek, unit="D")
    returns["week_starting"] = returns["invoice_date"].dt.normalize() - pd.to_timedelta(returns["invoice_date"].dt.dayofweek, unit="D")
    weekly = sales.groupby("week_starting").agg(
        gross_revenue=("line_revenue", "sum"),
        orders=("invoice", "nunique"),
        units=("quantity", "sum"),
        active_customers=("customer_id", "nunique"),
    )
    wrefunds = returns.groupby("week_starting")["refund_amount"].sum()
    weekly["refunds"] = wrefunds.reindex(weekly.index).fillna(0.0)
    weekly["net_revenue"] = weekly["gross_revenue"] - weekly["refunds"]
    weekly = weekly.reset_index()
    return monthly, weekly


def build_cohorts(sales):
    known = sales[sales["customer_id"].notna()].copy()
    known["cohort"] = known.groupby("customer_id")["invoice_date"].transform("min").dt.strftime("%Y-%m")
    known["activity_month"] = known["invoice_date"].dt.strftime("%Y-%m")
    month_index = (
        pd.to_datetime(known["activity_month"] + "-01") - pd.to_datetime(known["cohort"] + "-01")
    ).dt.days // 30
    known["month_index"] = month_index.astype(int)
    cohorts = known.groupby(["cohort", "month_index"])["customer_id"].nunique().unstack(fill_value=0)
    retention = cohorts.div(cohorts.iloc[:, 0], axis=0).round(4)
    retention = retention.reset_index().rename(columns={"cohort": "cohort_month"})
    return retention


def build_inventory_features(sales, dim_product, snapshot):
    features = sales.groupby("stockcode").agg(
        units_sold=("quantity", "sum"),
        orders=("invoice", "nunique"),
        last_sale=("invoice_date", "max"),
        first_sale=("invoice_date", "min"),
    ).reset_index()
    one_year_back = snapshot - pd.Timedelta(days=365)
    recent = sales[sales["invoice_date"] > one_year_back].copy()
    recent["week"] = recent["invoice_date"].dt.to_period("W").dt.start_time
    weekly_units = recent.groupby(["stockcode", "week"])["quantity"].sum().reset_index()
    all_weeks = pd.period_range(one_year_back, snapshot, freq="W").start_time
    full_index = pd.MultiIndex.from_product([features["stockcode"], all_weeks], names=["stockcode", "week"])
    weekly_units = weekly_units.set_index(["stockcode", "week"]).reindex(full_index, fill_value=0).reset_index()
    gaps = weekly_units[weekly_units["quantity"] == 0].groupby("stockcode").size()
    features["stockout_weeks_52w"] = features["stockcode"].map(gaps).fillna(0).astype(int)
    weekly_avg = weekly_units.groupby("stockcode")["quantity"].mean()
    features["avg_weekly_units"] = features["stockcode"].map(weekly_avg).round(2)
    features["days_since_last_sale"] = (snapshot - features["last_sale"].dt.normalize()).dt.days
    features = features.merge(dim_product[["stockcode", "description", "category", "is_service"]], on="stockcode", how="left")
    features["reorder_point_units"] = (features["avg_weekly_units"] * 2).round(0)
    product_mask = ~features["is_service"].fillna(False)
    active_mask = product_mask & (features["days_since_last_sale"] <= 90)
    q80 = features.loc[active_mask, "avg_weekly_units"].quantile(0.8)
    q20 = features.loc[active_mask, "avg_weekly_units"].quantile(0.2)
    conditions = [
        features["is_service"].fillna(False),
        features["days_since_last_sale"] > 90,
        active_mask & (features["avg_weekly_units"] >= q80),
        active_mask & (features["avg_weekly_units"] <= q20),
    ]
    features["movement_class"] = np.select(conditions, ["Service", "Dead Stock", "Fast Mover", "Slow Mover"], default="Normal")
    return features


def build_kpi_summary(sales, returns, customer_features, product_features, monthly, snapshot):
    yoy = monthly.copy()
    yoy["year"] = yoy["year_month"].str[:4]
    yearly = yoy.groupby("year")["net_revenue"].sum()
    latest_full_year = "2011"
    prior_year = "2010"
    gross = sales["line_revenue"].sum()
    refunds = returns["refund_amount"].sum()
    known = sales[sales["customer_id"].notna()]
    kpis = {
        "snapshot_date": str(snapshot.date()),
        "gross_revenue": round(float(gross), 2),
        "returns_refunds": round(float(refunds), 2),
        "net_revenue": round(float(gross - refunds), 2),
        "orders": int(sales["invoice"].nunique()),
        "lines": int(len(sales)),
        "customers_with_id": int(sales["customer_id"].nunique()),
        "products": int(sales[~sales["is_service"]]["stockcode"].nunique()),
        "countries": int(sales["country"].nunique()),
        "aov": round(float((gross - refunds) / sales["invoice"].nunique()), 2),
        "return_rate_pct": round(float(refunds / gross * 100), 2),
        "net_revenue_2010": round(float(yearly.get(prior_year, 0)), 2),
        "net_revenue_2011_partial": round(float(yearly.get(latest_full_year, 0)), 2),
        "yoy_growth_pct": round(float((yearly.get(latest_full_year, 0) / yearly.get(prior_year, 1) - 1) * 100), 1),
        "guest_line_share_pct": round(float(sales["customer_id"].isna().mean() * 100), 1),
        "churn_rate_pct": round(float(customer_features["churned"].mean() * 100), 1),
        "top_country_share_pct": round(float(sales.groupby("country")["line_revenue"].sum().max() / gross * 100), 1),
        "dead_stock_products": int((product_features["days_since_last_sale"] > 90).sum()),
        "total_products": int(len(product_features)),
    }
    with open(PROCESSED_DIR / "kpi_summary.json", "w") as fh:
        json.dump(kpis, fh, indent=2)
    return kpis


def run():
    sales, returns = load_facts()
    snapshot = sales["invoice_date"].max().normalize()
    dim_date = build_dim_date(sales)
    dim_product = build_dim_product(sales, returns)
    dim_customer = build_dim_customer(sales, returns, snapshot)
    dim_country = build_dim_country(sales)
    customer_features = build_customer_features(sales, returns, dim_customer, dim_product, snapshot)
    product_features = build_product_features(sales, returns, dim_product, snapshot)
    monthly, weekly = build_time_series(sales, returns)
    cohorts = build_cohorts(sales)
    inventory_features = build_inventory_features(sales, dim_product, snapshot)

    dim_date.to_parquet(PROCESSED_DIR / "dim_date.parquet", index=False)
    dim_product.to_parquet(PROCESSED_DIR / "dim_product.parquet", index=False)
    dim_customer.to_parquet(PROCESSED_DIR / "dim_customer.parquet", index=False)
    dim_country.to_parquet(PROCESSED_DIR / "dim_country.parquet", index=False)
    customer_features.to_parquet(PROCESSED_DIR / "customer_features.parquet", index=False)
    product_features.to_parquet(PROCESSED_DIR / "product_features.parquet", index=False)
    monthly.to_parquet(PROCESSED_DIR / "monthly_series.parquet", index=False)
    weekly.to_parquet(PROCESSED_DIR / "weekly_series.parquet", index=False)
    cohorts.to_parquet(PROCESSED_DIR / "cohort_retention.parquet", index=False)
    inventory_features.to_parquet(PROCESSED_DIR / "inventory_features.parquet", index=False)

    kpis = build_kpi_summary(sales, returns, customer_features, product_features, monthly, snapshot)
    return kpis


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
