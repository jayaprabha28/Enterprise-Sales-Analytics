"""Profitability, pricing/discount and inventory analytics on the cleaned sales data."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from config import FIGURES_DIR, PROCESSED_DIR, SQL_RESULTS_DIR


def load_frames():
    sales = pd.read_parquet(PROCESSED_DIR / "fact_sales.parquet")
    returns = pd.read_parquet(PROCESSED_DIR / "fact_returns.parquet")
    sales["invoice_date"] = pd.to_datetime(sales["invoice_date"])
    returns["invoice_date"] = pd.to_datetime(returns["invoice_date"])
    dim_product = pd.read_parquet(PROCESSED_DIR / "dim_product.parquet")
    product_features = pd.read_parquet(PROCESSED_DIR / "product_features.parquet")
    customer_segments = pd.read_parquet(PROCESSED_DIR / "customer_segments.parquet")
    inventory = pd.read_parquet(PROCESSED_DIR / "inventory_features.parquet")
    return sales, returns, dim_product, product_features, customer_segments, inventory


def profitability(sales, returns, dim_product):
    gross = float(sales["line_revenue"].sum())
    refunds = float(returns["refund_amount"].sum())
    by_year = sales.assign(year=sales["invoice_date"].dt.year).groupby("year")["line_revenue"].sum()
    refunds_by_year = returns.assign(year=returns["invoice_date"].dt.year).groupby("year")["refund_amount"].sum()
    waterfall = []
    for year in sorted(set(by_year.index) | set(refunds_by_year.index)):
        g = float(by_year.get(year, 0.0))
        r = float(refunds_by_year.get(year, 0.0))
        waterfall.append({"year": int(year), "gross_revenue": round(g, 2), "refunds": round(r, 2),
                          "net_revenue": round(g - r, 2), "realization_pct": round((g - r) / g * 100, 2) if g else None})

    product_lines = sales[~sales["is_service"]].merge(dim_product[["stockcode", "category"]], on="stockcode", how="left")
    cat_gross = product_lines.groupby("category")["line_revenue"].sum()
    cat_refunds = returns.merge(dim_product[["stockcode", "category"]], on="stockcode", how="left").groupby("category")["refund_amount"].sum()
    category = pd.DataFrame({"gross_revenue": cat_gross, "refunds": cat_refunds.reindex(cat_gross.index).fillna(0.0)})
    category["net_revenue"] = category["gross_revenue"] - category["refunds"]
    category["realization_pct"] = (category["net_revenue"] / category["gross_revenue"] * 100).round(2)
    category["share_pct"] = (category["net_revenue"] / category["net_revenue"].sum() * 100).round(2)
    category = category.sort_values("net_revenue", ascending=False).reset_index()
    category["cum_share_pct"] = category["share_pct"].cumsum().round(2)

    customers = pd.read_parquet(PROCESSED_DIR / "customer_segments.parquet")
    monetary = customers["monetary"].sort_values(ascending=False)
    total = monetary.sum()
    concentration = {
        "top_1pct_customers_share_pct": round(float(monetary.head(int(len(monetary) * 0.01)).sum() / total * 100), 1),
        "top_10pct_customers_share_pct": round(float(monetary.head(int(len(monetary) * 0.10)).sum() / total * 100), 1),
        "top_20pct_customers_share_pct": round(float(monetary.head(int(len(monetary) * 0.20)).sum() / total * 100), 1),
    }
    return waterfall, category, concentration, round(gross, 2), round(refunds, 2)


def pricing_discount(sales, dim_product):
    typical = dim_product.set_index("stockcode")["typical_price"]
    lines = sales[~sales["is_service"]].merge(dim_product[["stockcode", "category"]], on="stockcode", how="left")
    lines["typical_price"] = lines["stockcode"].map(typical)
    lines = lines[lines["typical_price"].notna() & (lines["typical_price"] > 0)]
    lines["discount_pct"] = (1 - lines["unit_price"] / lines["typical_price"]) * 100
    lines["price_position"] = np.select(
        [lines["discount_pct"] <= -5, lines["discount_pct"] <= 5, lines["discount_pct"] <= 10,
         lines["discount_pct"] <= 25],
        ["Premium", "Standard", "Light Discount", "Discount"],
        default="Deep Discount",
    )

    by_category = (
        lines.groupby(["category", "price_position"])["line_revenue"].sum().unstack(fill_value=0.0)
    )
    share = by_category.div(by_category.sum(axis=1), axis=0) * 100
    share = share.round(2).reset_index()

    position_totals = lines.groupby("price_position").agg(
        revenue=("line_revenue", "sum"), lines=("line_id", "count"), units=("quantity", "sum"),
        avg_discount_pct=("discount_pct", "mean"),
    ).reset_index()
    position_totals["revenue_share_pct"] = (
        position_totals["revenue"] / position_totals["revenue"].sum() * 100
    ).round(2)

    customers = pd.read_parquet(PROCESSED_DIR / "customer_segments.parquet")
    median_discount = customers["avg_discount_pct"].median()
    customers["discount_group"] = np.where(customers["avg_discount_pct"] > 0.05, "High Discount (>5%)", "Standard/Low")
    discount_behaviour = customers.groupby("discount_group").agg(
        customers=("customer_id", "count"),
        avg_monetary=("monetary", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_units_per_order=("avg_units_per_order", "mean"),
        churn_rate_pct=("churned", lambda s: round(float(s.mean() * 100), 1)),
        avg_discount_pct=("avg_discount_pct", "mean"),
    ).reset_index().round(3)

    summary = {
        "median_customer_discount_pct": round(float(median_discount * 100), 2),
        "discounted_revenue_share_pct": round(float(
            position_totals.loc[position_totals["price_position"].isin(["Light Discount", "Discount", "Deep Discount"]), "revenue_share_pct"].sum()
        ), 1),
        "avg_discount_depth_pct": round(float(
            lines.loc[lines["discount_pct"] > 5, "discount_pct"].mean()
        ), 1),
        "deep_discount_revenue": round(float(
            position_totals.loc[position_totals["price_position"] == "Deep Discount", "revenue"].iloc[0]
        ), 2) if (position_totals["price_position"] == "Deep Discount").any() else 0.0,
        "discount_behaviour": discount_behaviour.to_dict(orient="records"),
    }
    churn_gap = None
    if len(discount_behaviour) == 2:
        churn_gap = round(float(
            discount_behaviour.loc[discount_behaviour["discount_group"] == "High Discount (>5%)", "churn_rate_pct"].iloc[0]
            - discount_behaviour.loc[discount_behaviour["discount_group"] == "Standard/Low", "churn_rate_pct"].iloc[0]
        ), 1)
    summary["discount_dependent_churn_gap_pp"] = churn_gap
    return share, position_totals, summary


def inventory_health(inventory):
    products = inventory[~inventory["is_service"].fillna(False)]
    class_stats = products.groupby("movement_class").agg(
        skus=("stockcode", "count"),
        avg_weekly_units=("avg_weekly_units", "mean"),
        avg_stockout_weeks=("stockout_weeks_52w", "mean"),
    ).round(2).reset_index()
    prior_year_revenue = pd.read_parquet(PROCESSED_DIR / "product_features.parquet")
    dead = prior_year_revenue[prior_year_revenue["days_since_last_sale"] > 90]
    chronic_stockout = products[
        (products["stockout_weeks_52w"] >= 8) & (products["avg_weekly_units"] >= 1)
    ]
    summary = {
        "product_skus": int(len(products)),
        "dead_stock_skus": int((products["days_since_last_sale"] > 90).sum()),
        "dead_stock_prior_year_revenue": round(float(dead["gross_revenue"].sum()), 2),
        "chronic_stockout_skus": int(len(chronic_stockout)),
        "fast_mover_skus": int((products["movement_class"] == "Fast Mover").sum()),
        "slow_mover_skus": int((products["movement_class"] == "Slow Mover").sum()),
        "avg_stockout_weeks": round(float(chronic_stockout["stockout_weeks_52w"].mean()), 1) if len(chronic_stockout) else 0.0,
        "top_chronic_stockout": chronic_stockout.sort_values(
            ["stockout_weeks_52w", "avg_weekly_units"], ascending=[False, False]
        ).head(10)[
            ["stockcode", "description", "category", "stockout_weeks_52w", "avg_weekly_units"]
        ].to_dict(orient="records"),
    }
    return class_stats, summary


def return_hotspots(sales, returns, dim_product):
    ref = returns.merge(dim_product[["stockcode", "category"]], on="stockcode", how="left")
    gross = sales[~sales["is_service"]].groupby("stockcode")["line_revenue"].sum()
    refunds = ref.groupby("stockcode")["refund_amount"].sum()
    units = sales.groupby("stockcode")["quantity"].sum()
    frame = pd.DataFrame({"gross": gross, "refunds": refunds.reindex(gross.index).fillna(0.0), "units": units})
    frame["return_rate_pct"] = (frame["refunds"] / frame["gross"] * 100).round(2)
    hotspots = frame[(frame["return_rate_pct"] > 10) & (frame["gross"] > 5000)].sort_values(
        "refunds", ascending=False
    ).reset_index()
    hotspots = hotspots.merge(dim_product[["stockcode", "description", "category"]], on="stockcode", how="left")
    return hotspots, round(float(frame["refunds"].sum() / frame["gross"].sum() * 100), 2)


def make_figures(category, share, position_totals, class_stats, discount_behaviour):
    sns.set_theme(style="whitegrid")

    fig, ax = plt.subplots(figsize=(12, 6))
    top = category.head(10)
    sns.barplot(data=top, x="net_revenue", y="category", ax=ax, color="#2ca02c")
    ax.set_title("Net Revenue by Product Category (top 10)")
    ax.set_xlabel("Net revenue (£)")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "profitability_by_category.png", dpi=130)
    plt.close(fig)

    order = ["Premium", "Standard", "Light Discount", "Discount", "Deep Discount"]
    plot_data = position_totals.set_index("price_position").reindex(order).dropna().reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sns.barplot(data=plot_data, x="price_position", y="revenue_share_pct", ax=axes[0], color="#1f77b4")
    axes[0].set_title("Share of Revenue by Price Position")
    axes[0].set_ylabel("% of revenue")
    axes[0].set_xlabel("")
    sns.barplot(data=share.melt(id_vars="category", var_name="price_position", value_name="share")
                .pipe(lambda d: d[d["price_position"].isin(["Discount", "Deep Discount"])]),
                x="share", y="category", hue="price_position", ax=axes[1])
    axes[1].legend(title="", fontsize=8)
    axes[1].set_title("Discounted Revenue Share by Category")
    axes[1].set_xlabel("% of category revenue on discount")
    axes[1].set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "pricing_discount_analysis.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(data=class_stats, x="movement_class", y="skus", ax=ax, color="#9467bd")
    ax.set_title("Product SKUs by Inventory Movement Class")
    ax.set_xlabel("")
    ax.set_ylabel("SKUs")
    for container in ax.containers:
        ax.bar_label(container)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "inventory_movement_classes.png", dpi=130)
    plt.close(fig)

    if len(discount_behaviour):
        fig, ax = plt.subplots(figsize=(9, 5))
        sns.barplot(data=discount_behaviour, x="discount_group", y="churn_rate_pct", ax=ax, color="#ff7f0e")
        ax.set_title("Churn Rate: High-Discount vs Standard Customers")
        ax.set_ylabel("Churn rate %")
        ax.set_xlabel("")
        for container in ax.containers:
            ax.bar_label(container, fmt="%.1f%%")
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "discount_vs_churn.png", dpi=130)
        plt.close(fig)


def run():
    sales, returns, dim_product, product_features, customer_segments, inventory = load_frames()
    waterfall, category, concentration, gross, refunds = profitability(sales, returns, dim_product)
    share, position_totals, pricing_summary = pricing_discount(sales, dim_product)
    class_stats, inventory_summary = inventory_health(inventory)
    hotspots, overall_return_rate = return_hotspots(sales, returns, dim_product)

    watchlist_path = SQL_RESULTS_DIR / "high_revenue_low_retention_watchlist.csv"
    watchlist = pd.read_csv(watchlist_path).head(8).to_dict(orient="records") if watchlist_path.exists() else []

    pd.DataFrame(waterfall).to_csv(PROCESSED_DIR / "profitability_waterfall.csv", index=False)
    category.to_csv(PROCESSED_DIR / "category_economics.csv", index=False)
    share.to_csv(PROCESSED_DIR / "discount_by_category.csv", index=False)
    position_totals.to_csv(PROCESSED_DIR / "price_position_totals.csv", index=False)
    class_stats.to_csv(PROCESSED_DIR / "inventory_class_stats.csv", index=False)
    hotspots.to_csv(PROCESSED_DIR / "return_hotspots.csv", index=False)

    summary = {
        "gross_revenue": gross,
        "returns_refunds": refunds,
        "net_revenue": round(gross - refunds, 2),
        "realization_pct": round((gross - refunds) / gross * 100, 2),
        "waterfall_by_year": waterfall,
        "concentration": concentration,
        "top_category_economics": category.head(6).to_dict(orient="records"),
        "pricing": pricing_summary,
        "inventory": inventory_summary,
        "overall_return_rate_pct": overall_return_rate,
        "return_hotspots_count": int(len(hotspots)),
        "top_return_hotspots": hotspots.head(5)[
            ["stockcode", "description", "gross", "refunds", "return_rate_pct"]
        ].to_dict(orient="records"),
        "watchlist": watchlist,
        "cogs_note": "No cost fields exist in the source dataset: margin is expressed as revenue realization (net of refunds) and price position, not gross margin.",
    }
    with open(PROCESSED_DIR / "analytics_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)

    make_figures(category, share, position_totals, class_stats,
                 pd.DataFrame(pricing_summary["discount_behaviour"]))
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("top_category_economics", "top_return_hotspots", "watchlist", "inventory")}, indent=2))
    return summary


if __name__ == "__main__":
    run()
