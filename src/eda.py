"""Exploratory data analysis: twelve report figures plus a machine-readable eda_summary.json."""

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import seaborn as sns

from config import FIGURES_DIR, PROCESSED_DIR

FIG_SIZE = (12, 6)
FIG_DPI = 130
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COHORT_MONTHS = [str(index) for index in range(13)]
CLASS_COLOURS = {"A": "#4c72b0", "B": "#dd8452", "C": "#55a868"}
COLOUR_SALE = "#4c72b0"
COLOUR_NET = "#55a868"
COLOUR_ALERT = "#c44e52"
COLOUR_SERVICE = "#9e9e9e"

sns.set_theme(style="whitegrid", context="notebook")


def money(value):
    return f"Â£{value:,.2f}"


def money_axis_format(value, position=None):
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"Â£{value / 1_000_000:,.1f}M"
    if magnitude >= 1_000:
        return f"Â£{value / 1_000:,.0f}k"
    return f"Â£{value:,.0f}"


def format_money_axis(axis, axis_name="y"):
    target = axis.yaxis if axis_name == "y" else axis.xaxis
    target.set_major_formatter(mticker.FuncFormatter(money_axis_format))


def shorten(text, limit=40):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "â€¦"


def label_bars_h(axis, values):
    spread = float(max(values)) - float(min(values))
    pad = spread * 0.015 if spread else float(max(values)) * 0.02
    for position, value in enumerate(values):
        axis.text(value + pad, position, money_axis_format(value), va="center", fontsize=8)


def save_figure(figure, filename):
    path = FIGURES_DIR / filename
    figure.savefig(path, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(figure)
    return path


def load_inputs():
    sales = pd.read_parquet(PROCESSED_DIR / "fact_sales.parquet")
    returns = pd.read_parquet(PROCESSED_DIR / "fact_returns.parquet")
    dim_date = pd.read_parquet(PROCESSED_DIR / "dim_date.parquet")
    dim_product = pd.read_parquet(PROCESSED_DIR / "dim_product.parquet")
    monthly = pd.read_parquet(PROCESSED_DIR / "monthly_series.parquet")
    cohort = pd.read_parquet(PROCESSED_DIR / "cohort_retention.parquet")
    product_features = pd.read_parquet(PROCESSED_DIR / "product_features.parquet")
    customer_features = pd.read_parquet(PROCESSED_DIR / "customer_features.parquet")
    sales["invoice_date"] = pd.to_datetime(sales["invoice_date"])
    returns["invoice_date"] = pd.to_datetime(returns["invoice_date"])
    sales = sales.merge(dim_date[["date_key", "day_of_week", "day_name"]], on="date_key", how="left")
    return {
        "sales": sales,
        "returns": returns,
        "dim_product": dim_product,
        "monthly": monthly,
        "cohort": cohort,
        "product_features": product_features,
        "customer_features": customer_features,
    }


def net_by(sales, returns, column):
    gross = sales.groupby(column)["line_revenue"].sum()
    refunds = returns.groupby(column)["refund_amount"].sum()
    return gross.subtract(refunds, fill_value=0.0).sort_values(ascending=False)


def category_tables(sales, returns, dim_product):
    product_map = dim_product[["stockcode", "category"]]
    sales_joined = sales.merge(product_map, on="stockcode", how="left")
    returns_joined = returns.merge(product_map, on="stockcode", how="left")
    gross = sales_joined.groupby("category")["line_revenue"].sum()
    refunds = returns_joined.groupby("category")["refund_amount"].sum()
    net = gross.subtract(refunds, fill_value=0.0).sort_values(ascending=False)
    return net, gross, refunds


def plot_revenue_trend_monthly(monthly):
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    positions = np.arange(len(monthly))
    width = 0.4
    axis.bar(positions - width / 2, monthly["gross_revenue"], width, label="Gross revenue", color=COLOUR_SALE)
    axis.bar(positions + width / 2, monthly["net_revenue"], width, label="Net revenue", color=COLOUR_NET)
    axis.plot(positions, monthly["net_revenue"], color=COLOUR_ALERT, marker="o", markersize=3, linewidth=1.6, label="Net revenue line")
    axis.set_xticks(positions)
    axis.set_xticklabels(monthly["year_month"], rotation=45, ha="right", fontsize=8)
    axis.set_ylabel("Revenue (GBP)")
    axis.set_title("Monthly Gross and Net Revenue (Dec 2009 - Dec 2011)")
    axis.legend(fontsize=9)
    format_money_axis(axis)
    figure.tight_layout()
    return save_figure(figure, "revenue_trend_monthly.png")


def plot_revenue_yoy_compare(monthly):
    frame = monthly.copy()
    frame["year"] = frame["year_month"].str[:4]
    frame["month_number"] = frame["year_month"].str[5:].astype(int)
    pivot = frame[frame["year"].isin(["2010", "2011"])].pivot(index="month_number", columns="year", values="net_revenue")
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    axis.plot(pivot.index, pivot["2010"], marker="o", color=COLOUR_SALE, linewidth=2, label="2010")
    axis.plot(pivot.index, pivot["2011"], marker="o", color=COLOUR_ALERT, linewidth=2, label="2011 (through 09-Dec)")
    axis.set_xticks(range(1, 13))
    axis.set_xticklabels(MONTH_NAMES)
    axis.set_xlabel("Calendar month")
    axis.set_ylabel("Net revenue (GBP)")
    axis.set_title("YoY Monthly Net Revenue: 2010 vs 2011 (2011 is partial, data only to 09-Dec)")
    axis.legend(fontsize=9)
    format_money_axis(axis)
    figure.tight_layout()
    return save_figure(figure, "revenue_yoy_compare.png")


def plot_top_countries(country_net):
    top = country_net.head(12).iloc[::-1]
    values = top.to_numpy()
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    axis.barh(np.arange(len(top)), values, color=COLOUR_SALE)
    axis.set_yticks(np.arange(len(top)))
    axis.set_yticklabels([str(name) for name in top.index])
    label_bars_h(axis, values)
    axis.set_xlabel("Net revenue (GBP)")
    axis.set_title("Top 12 Countries by Net Revenue")
    format_money_axis(axis)
    figure.tight_layout()
    return save_figure(figure, "top_countries.png")


def plot_top_products(product_features):
    top = product_features.loc[~product_features["is_service"]].nlargest(12, "net_revenue").iloc[::-1]
    values = top["net_revenue"].to_numpy()
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    axis.barh(np.arange(len(top)), values, color=COLOUR_NET)
    axis.set_yticks(np.arange(len(top)))
    axis.set_yticklabels([shorten(description) for description in top["description"]])
    label_bars_h(axis, values)
    axis.set_xlabel("Net revenue (GBP)")
    axis.set_title("Top 12 Non-Service Products by Net Revenue")
    format_money_axis(axis)
    figure.tight_layout()
    return save_figure(figure, "top_products.png")


def plot_abc_pareto(product_features):
    ordered = product_features.sort_values("gross_revenue", ascending=False).reset_index(drop=True)
    total_revenue = ordered["gross_revenue"].sum()
    top = ordered.head(40)
    cumulative = ordered["gross_revenue"].cumsum().head(40) / total_revenue * 100
    colours = [CLASS_COLOURS.get(str(label), COLOUR_SERVICE) for label in top["abc_class"]]
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    axis.bar(np.arange(len(top)), top["gross_revenue"], color=colours)
    axis.set_ylabel("Revenue (GBP)")
    axis.set_xticks(np.arange(len(top)))
    axis.set_xticklabels(top["stockcode"], rotation=90, fontsize=7)
    share_axis = axis.twinx()
    share_axis.plot(np.arange(len(top)), cumulative, color="black", marker="o", markersize=3, linewidth=1.5)
    share_axis.axhline(80, color="grey", linestyle="--", linewidth=1.2)
    share_axis.axhline(95, color="darkgrey", linestyle=":", linewidth=1.2)
    share_axis.set_ylim(0, 100)
    share_axis.set_ylabel("Cumulative share of total revenue (%)")
    handles = [Patch(color=CLASS_COLOURS[key], label=f"ABC class {key}") for key in ("A", "B", "C")]
    handles += [
        Line2D([0], [0], color="black", marker="o", markersize=3, label="Cumulative % share"),
        Line2D([0], [0], color="grey", linestyle="--", label="80% reference"),
        Line2D([0], [0], color="darkgrey", linestyle=":", label="95% reference"),
    ]
    axis.legend(handles=handles, loc="lower right", fontsize=8)
    axis.set_title("ABC Pareto: Top 40 Products by Revenue with Cumulative Share")
    format_money_axis(axis)
    figure.tight_layout()
    return save_figure(figure, "abc_pareto.png")


def plot_new_vs_returning(monthly):
    positions = np.arange(len(monthly))
    new_customers = monthly["new_customers"].to_numpy()
    returning_customers = monthly["returning_customers"].to_numpy()
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    axis.bar(positions, new_customers, label="New customers", color=COLOUR_SALE)
    axis.bar(positions, returning_customers, bottom=new_customers, label="Returning customers", color=COLOUR_NET)
    totals = new_customers + returning_customers
    share = np.where(totals > 0, new_customers / np.where(totals > 0, totals, 1) * 100, 0.0)
    share_axis = axis.twinx()
    share_axis.plot(positions, share, color=COLOUR_ALERT, marker="o", markersize=3, linewidth=1.6, label="New customer share (%)")
    share_axis.set_ylim(0, 108)
    share_axis.set_ylabel("New customer share (%)")
    axis.set_xticks(positions)
    axis.set_xticklabels(monthly["year_month"], rotation=45, ha="right", fontsize=8)
    axis.set_ylabel("Active customers")
    axis.set_title("Monthly New vs Returning Customers with New Customer Share")
    handles, labels = axis.get_legend_handles_labels()
    share_handles, share_labels = share_axis.get_legend_handles_labels()
    axis.legend(handles + share_handles, labels + share_labels, fontsize=9, loc="upper right")
    figure.tight_layout()
    return save_figure(figure, "new_vs_returning.png")


def plot_aov_distribution(invoice_totals):
    figure, (hist_axis, box_axis) = plt.subplots(1, 2, figsize=FIG_SIZE)
    positive = invoice_totals.loc[invoice_totals["total"] > 0, "total"]
    bins = np.logspace(np.log10(positive.min()), np.log10(positive.max()), 40)
    hist_axis.hist(positive, bins=bins, color=COLOUR_SALE, edgecolor="white")
    hist_axis.set_xscale("log")
    hist_axis.set_xlabel("Invoice total (GBP, log10 scale)")
    hist_axis.set_ylabel("Number of invoices")
    median_total = float(invoice_totals["total"].median())
    hist_axis.axvline(median_total, color=COLOUR_ALERT, linestyle="--", linewidth=1.5)
    hist_axis.annotate(
        f"Median AOV {money(median_total)}",
        xy=(median_total, 0.92),
        xycoords=("data", "axes fraction"),
        xytext=(8, 0),
        textcoords="offset points",
        color=COLOUR_ALERT,
        fontsize=9,
        va="center",
    )
    hist_axis.xaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _: f"Â£{value:,.0f}"))
    hist_axis.set_title("Invoice totals, log10 scale")

    window = invoice_totals.loc[invoice_totals["year"].isin([2010, 2011])].copy()
    window["year"] = window["year"].astype(str)
    sns.boxplot(data=window, x="year", y="total", showfliers=False, color="#9ecae1", ax=box_axis)
    medians = window.groupby("year")["total"].median()
    for position, year in enumerate(["2010", "2011"]):
        value = float(medians[year])
        box_axis.annotate(
            money(value),
            xy=(position + 0.32, value),
            fontsize=9,
            va="center",
            color=COLOUR_ALERT,
        )
    box_axis.set_xlabel("Year")
    box_axis.set_ylabel("Invoice total (GBP)")
    box_axis.set_title("Invoice totals by year (2010 and 2011)")
    format_money_axis(box_axis)
    figure.tight_layout()
    return save_figure(figure, "aov_distribution.png")


def plot_return_rate_trend(monthly):
    frame = monthly.copy()
    frame["refund_rate"] = frame["refunds"] / frame["gross_revenue"] * 100
    frame["moving_average"] = frame["refund_rate"].rolling(3, min_periods=1).mean()
    positions = np.arange(len(frame))
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    axis.bar(positions, frame["refund_rate"], color=COLOUR_SALE, label="Monthly refund rate")
    axis.plot(positions, frame["moving_average"], color=COLOUR_ALERT, marker="o", markersize=3, linewidth=1.8, label="3-month moving average")
    axis.set_xticks(positions)
    axis.set_xticklabels(frame["year_month"], rotation=45, ha="right", fontsize=8)
    axis.set_ylabel("Refunds as % of gross revenue")
    axis.set_title("Monthly Refund Rate (% of Gross Revenue) with 3-Month Moving Average")
    axis.legend(fontsize=9)
    figure.tight_layout()
    return save_figure(figure, "return_rate_trend.png")


def plot_weekday_pattern(sales):
    weekday = sales.groupby("day_of_week").agg(
        revenue=("line_revenue", "sum"),
        orders=("invoice", "nunique"),
        day_name=("day_name", "first"),
    )
    positions = np.arange(len(weekday))
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    axis.bar(positions, weekday["revenue"], color=COLOUR_SALE, label="Revenue")
    axis.set_xticks(positions)
    axis.set_xticklabels(weekday["day_name"])
    axis.set_ylabel("Revenue (GBP)")
    order_value_axis = axis.twinx()
    order_value_axis.plot(positions, weekday["revenue"] / weekday["orders"], color=COLOUR_ALERT, marker="o", linewidth=1.8, label="Average order value")
    order_value_axis.set_ylabel("Average order value (GBP)")
    format_money_axis(axis)
    format_money_axis(order_value_axis)
    axis.set_title("Revenue and Average Order Value by Weekday")
    handles, labels = axis.get_legend_handles_labels()
    order_handles, order_labels = order_value_axis.get_legend_handles_labels()
    axis.legend(handles + order_handles, labels + order_labels, fontsize=9, loc="upper right")
    figure.tight_layout()
    return save_figure(figure, "weekday_pattern.png")


def plot_category_mix(category_net, service_categories):
    ordered = category_net.sort_values()
    values = ordered.to_numpy()
    colours = [COLOUR_SERVICE if str(name) in service_categories else COLOUR_SALE for name in ordered.index]
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    axis.barh(np.arange(len(ordered)), values, color=colours)
    axis.set_yticks(np.arange(len(ordered)))
    axis.set_yticklabels([shorten(str(name), 34) for name in ordered.index], fontsize=8)
    label_bars_h(axis, values)
    axis.set_xlabel("Net revenue (GBP)")
    axis.set_title("Net Revenue by Product Category (service categories in grey)")
    handles = [
        Patch(color=COLOUR_SALE, label="Product categories"),
        Patch(color=COLOUR_SERVICE, label="Service categories"),
    ]
    axis.legend(handles=handles, loc="lower right", fontsize=9)
    format_money_axis(axis)
    figure.tight_layout()
    return save_figure(figure, "category_mix.png")


def plot_cohort_heatmap(cohort):
    retention = cohort.set_index("cohort_month")[COHORT_MONTHS].astype(float) * 100
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    sns.heatmap(
        retention,
        cmap="YlOrRd",
        annot=False,
        ax=axis,
        linewidths=0.3,
        linecolor="white",
        cbar_kws={"label": "Retention (% of cohort active)"},
    )
    annotated_rows = min(12, len(retention))
    for row in range(annotated_rows):
        for column_index, column_name in enumerate(COHORT_MONTHS):
            value = retention.iat[row, column_index]
            axis.text(
                column_index + 0.5,
                row + 0.5,
                f"{value:.0f}",
                ha="center",
                va="center",
                fontsize=6,
                color="white" if value >= 60 else "black",
            )
    axis.set_xlabel("Months since first purchase")
    axis.set_ylabel("Cohort month")
    axis.set_title("Cohort Retention Heatmap (% active; first 12 cohorts annotated)")
    figure.tight_layout()
    return save_figure(figure, "cohort_retention_heatmap.png")


def plot_customer_recency_frequency(customer_features):
    figure, axis = plt.subplots(figsize=FIG_SIZE)
    for flag, label, colour in [(0, "Active", COLOUR_SALE), (1, "Churned", COLOUR_ALERT)]:
        segment = customer_features.loc[customer_features["churned"] == flag]
        axis.scatter(
            segment["recency_days"],
            segment["frequency"],
            s=14,
            alpha=0.4,
            color=colour,
            edgecolors="none",
            label=label,
        )
    axis.set_xlabel("Recency (days since last purchase)")
    axis.set_ylabel("Frequency (orders)")
    axis.set_title("Customer Recency vs Frequency, coloured by churn status")
    axis.legend(fontsize=9)
    figure.tight_layout()
    return save_figure(figure, "customer_recency_frequency.png")


def window_net_revenue(sales, returns, year):
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year, month=12, day=9)
    sales_window = sales["invoice_date"].dt.normalize().between(start, end)
    returns_window = returns["invoice_date"].dt.normalize().between(start, end)
    return float(sales.loc[sales_window, "line_revenue"].sum() - returns.loc[returns_window, "refund_amount"].sum())


def build_summary(sales, returns, monthly, cohort, product_features, customer_features, invoice_totals, category_net, category_gross, category_refunds):
    best_row = monthly.loc[monthly["net_revenue"].idxmax()]
    complete = monthly[monthly["year_month"] != monthly["year_month"].max()]
    worst_row = complete.loc[complete["net_revenue"].idxmin()]
    revenue_2010 = window_net_revenue(sales, returns, 2010)
    revenue_2011 = window_net_revenue(sales, returns, 2011)
    total_net = float(sales["line_revenue"].sum() - returns["refund_amount"].sum())
    region_net = net_by(sales, returns, "region")
    country_net = net_by(sales, returns, "country")
    top_region_value = float(region_net.iloc[0])
    top_country_value = float(country_net.iloc[0])
    top_category_value = float(category_net.iloc[0])
    top_product = product_features.loc[product_features["net_revenue"].idxmax()]
    known = sales.loc[sales["customer_id"].notna()].copy()
    first_months = known.groupby("customer_id")["invoice_date"].min().dt.strftime("%Y-%m")
    known["first_month"] = known["customer_id"].map(first_months)
    known["sale_month"] = known["invoice_date"].dt.strftime("%Y-%m")
    known_revenue = float(known["line_revenue"].sum())
    new_revenue = float(known.loc[known["first_month"] == known["sale_month"], "line_revenue"].sum())
    weekday = sales.groupby("day_of_week").agg(revenue=("line_revenue", "sum"), day_name=("day_name", "first"))
    refund_rates = (category_refunds / category_gross * 100).where(category_gross > 10000).dropna().sort_values(ascending=False).head(5)
    guest_revenue = float(sales.loc[sales["customer_id"].isna(), "line_revenue"].sum())
    gross_revenue = float(sales["line_revenue"].sum())
    cohort_sizes = first_months.value_counts()
    retention_by_cohort = cohort.set_index("cohort_month")["3"].astype(float)
    common_cohorts = retention_by_cohort.index.intersection(cohort_sizes.index)
    eligible_retention = retention_by_cohort.loc[common_cohorts][cohort_sizes.reindex(common_cohorts) >= 50]
    growth = (revenue_2011 / revenue_2010 - 1) * 100 if revenue_2010 else float("nan")
    summary = {
        "best_sales_month": {"year_month": str(best_row["year_month"]), "net_revenue": round(float(best_row["net_revenue"]), 2)},
        "worst_sales_month": {"year_month": str(worst_row["year_month"]), "net_revenue": round(float(worst_row["net_revenue"]), 2)},
        "yoy_like_for_like": {
            "revenue_2010_jan_dec9": round(revenue_2010, 2),
            "revenue_2011_jan_dec9": round(revenue_2011, 2),
            "growth_pct": round(float(growth), 2),
        },
        "top_region": {
            "region": str(region_net.index[0]),
            "net_revenue": round(top_region_value, 2),
            "share_pct": round(top_region_value / total_net * 100, 2),
        },
        "top_country": {
            "country": str(country_net.index[0]),
            "net_revenue": round(top_country_value, 2),
            "share_pct": round(top_country_value / total_net * 100, 2),
        },
        "top_category": {
            "category": str(category_net.index[0]),
            "net_revenue": round(top_category_value, 2),
            "share_pct": round(top_category_value / total_net * 100, 2),
        },
        "top_product": {
            "stockcode": str(top_product["stockcode"]),
            "description": str(top_product["description"]),
            "net_revenue": round(float(top_product["net_revenue"]), 2),
        },
        "aov": {
            "mean": round(float(invoice_totals["total"].mean()), 2),
            "median": round(float(invoice_totals["total"].median()), 2),
            "p90": round(float(invoice_totals["total"].quantile(0.9)), 2),
        },
        "new_vs_returning_share": {
            "new_customer_revenue_pct": round(new_revenue / known_revenue * 100, 2),
            "returning_customer_revenue_pct": round((known_revenue - new_revenue) / known_revenue * 100, 2),
        },
        "peak_weekday": {"day_name": str(weekday["day_name"].loc[weekday["revenue"].idxmax()]), "revenue": round(float(weekday["revenue"].max()), 2)},
        "low_weekday": {"day_name": str(weekday["day_name"].loc[weekday["revenue"].idxmin()]), "revenue": round(float(weekday["revenue"].min()), 2)},
        "return_rate_by_category": {str(name): round(float(value), 2) for name, value in refund_rates.items()},
        "guest_revenue_share_pct": round(guest_revenue / gross_revenue * 100, 2),
        "customer_base": {
            "churned_pct": round(float(customer_features["churned"].mean() * 100), 2),
            "avg_recency_days": round(float(customer_features["recency_days"].mean()), 1),
            "median_frequency": round(float(customer_features["frequency"].median()), 2),
            "median_monetary": round(float(customer_features["monetary"].median()), 2),
        },
        "cohort_best_retention_pct": round(float(eligible_retention.max() * 100), 2),
        "product_health": {
            "dead_stock_count": int((product_features["days_since_last_sale"] > 90).sum()),
            "declining_products_90d_count": int((product_features["growth_90d_pct"] < -20).sum()),
            "growing_products_90d_count": int((product_features["growth_90d_pct"] > 20).sum()),
        },
        "top5_categories": [
            {"category": str(name), "net_revenue": round(float(value), 2)}
            for name, value in category_net.head(5).items()
        ],
    }
    return summary


def run():
    data = load_inputs()
    sales = data["sales"]
    returns = data["returns"]
    monthly = data["monthly"]
    dim_product = data["dim_product"]
    cohort = data["cohort"]
    product_features = data["product_features"]
    customer_features = data["customer_features"]

    invoice_totals = (
        sales.groupby("invoice")
        .agg(total=("line_revenue", "sum"), first_date=("invoice_date", "min"))
        .reset_index()
    )
    invoice_totals["year"] = invoice_totals["first_date"].dt.year
    category_net, category_gross, category_refunds = category_tables(sales, returns, dim_product)
    country_net = net_by(sales, returns, "country")
    service_categories = set(dim_product.loc[dim_product["is_service"], "category"].unique())

    plot_revenue_trend_monthly(monthly)
    plot_revenue_yoy_compare(monthly)
    plot_top_countries(country_net)
    plot_top_products(product_features)
    plot_abc_pareto(product_features)
    plot_new_vs_returning(monthly)
    plot_aov_distribution(invoice_totals)
    plot_return_rate_trend(monthly)
    plot_weekday_pattern(sales)
    plot_category_mix(category_net, service_categories)
    plot_cohort_heatmap(cohort)
    plot_customer_recency_frequency(customer_features)

    summary = build_summary(
        sales,
        returns,
        monthly,
        cohort,
        product_features,
        customer_features,
        invoice_totals,
        category_net,
        category_gross,
        category_refunds,
    )
    with open(PROCESSED_DIR / "eda_summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
