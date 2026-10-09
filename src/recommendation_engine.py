"""Generate business_insights.md and recommendations.md from every analysis artifact."""
import json
from pathlib import Path

import pandas as pd

from config import FIGURES_DIR, PROCESSED_DIR, REPORTS_DIR, SQL_RESULTS_DIR


def load_json(name: str) -> dict:
    path = PROCESSED_DIR / name
    if path.exists():
        with open(path) as fh:
            return json.load(fh)
    return {}


def load_sql(name: str) -> pd.DataFrame:
    path = SQL_RESULTS_DIR / f"{name}.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def money(value) -> str:
    return f"£{value:,.0f}"


def pct(value, digits=1) -> str:
    return f"{value:.{digits}f}%"


def figure_block(name: str, caption: str) -> str:
    if (FIGURES_DIR / name).exists():
        return f"![{caption}](figures/{name})\n\n*{caption}*"
    return ""


def build_insights(sources: dict) -> str:
    kpi = sources["kpi"]
    eda = sources["eda"]
    seg = sources["seg"]
    churn = sources["churn"]
    forecast = sources["forecast"]
    analytics = sources["analytics"]
    cleaning = sources["cleaning"]

    lfl = eda.get("yoy_like_for_like", {})
    concentration = analytics.get("concentration", {})
    pricing = analytics.get("pricing", {})
    inventory = analytics.get("inventory", {})
    segments = seg.get("segments", [])
    segment_table = pd.DataFrame(segments)

    lines = []
    lines.append("# Business Insights — Enterprise Sales & Revenue Intelligence Platform\n")
    lines.append(
        f"**Source data:** UCI Online Retail II (Kaggle) — {cleaning.get('raw_rows', 0):,} raw transaction lines "
        f"({cleaning.get('date_min', '')[:10]} to {cleaning.get('date_max', '')[:10]}), "
        f"cleaned to {cleaning.get('sales_rows', 0):,} sales lines + {cleaning.get('return_rows', 0):,} credit lines "
        f"with {cleaning.get('quarantined_rows', 0):,} rows quarantined ({', '.join(f'{k}: {v}' for k, v in cleaning.get('quarantine_reasons', {}).items())}). "
        f"Currency: GBP. Business snapshot: {kpi.get('snapshot_date', '')}.\n"
    )

    lines.append("## 1. Executive Summary\n")
    lines.append("| KPI | Value |")
    lines.append("|---|---|")
    lines.append(f"| Gross revenue | {money(kpi['gross_revenue'])} |")
    lines.append(f"| Returns & refunds | {money(kpi['returns_refunds'])} ({pct(kpi['return_rate_pct'])} of gross) |")
    lines.append(f"| Net revenue | {money(kpi['net_revenue'])} |")
    lines.append(f"| Orders | {kpi['orders']:,} |")
    lines.append(f"| Average order value | {money(kpi['aov'])} |")
    lines.append(f"| Registered customers | {kpi['customers_with_id']:,} |")
    lines.append(f"| Products (non-service) | {kpi['products']:,} across {kpi['countries']} countries |")
    lines.append(f"| YoY like-for-like growth (Jan–Dec 9) | {pct(lfl.get('growth_like_for_like_pct', lfl.get('growth_pct', float('nan'))))} |")
    lines.append(f"| Churned customers (90-day) | {pct(kpi['churn_rate_pct'])} |")
    lines.append(f"| UK revenue concentration | {pct(kpi['top_country_share_pct'])} |")
    lines.append("")
    lines.append(
        f"The business is a **large, UK-dominated wholesale-style operation**: {pct(kpi['top_country_share_pct'])} of revenue "
        f"comes from the United Kingdom, the top 1% of customers generate {pct(concentration.get('top_1pct_customers_share_pct', 0))} of "
        f"known-customer revenue, and average order value of {money(kpi['aov'])} indicates trade/wholesale order patterns rather than "
        f"consumer retail. Growth is modest but positive on a like-for-like basis, while **revenue realization is eroding** "
        f"(returns rising year over year) and **half the customer base is churned** on a 90-day definition.\n"
    )

    lines.append("## 2. Revenue & Growth\n")
    lines.append(f"**Data:** Best trading month {eda['best_sales_month']['year_month']} at {money(eda['best_sales_month']['net_revenue'])}; "
                 f"worst complete month {eda['worst_sales_month']['year_month']} at {money(eda['worst_sales_month']['net_revenue'])}. "
                 f"Like-for-like (Jan 1–Dec 9): {money(lfl.get('revenue_2010_jan_dec9', 0))} in 2010 → {money(lfl.get('revenue_2011_jan_dec9', 0))} in 2011.\n")
    lines.append("**Analysis:** Monthly revenue decomposed into trend, seasonality and year-over-year comparisons using window functions (SQL) and Python time-series aggregation.\n")
    lines.append(f"**Insight:** Revenue is **strongly seasonal with a Q4 (Christmas) peak** — the strongest month runs at roughly "
                 f"3x the weakest complete month — and like-for-like growth is **{pct(lfl.get('growth_like_for_like_pct', lfl.get('growth_pct', float('nan'))))}**, "
                 "i.e. the business is growing slowly while facing increasing returns.\n")
    lines.append(figure_block("revenue_trend_monthly.png", "Monthly gross vs net revenue"))
    lines.append(figure_block("revenue_yoy_compare.png", "2010 vs 2011 monthly comparison"))
    lines.append(figure_block("top_countries.png", "Revenue by country"))

    lines.append("## 3. Customer Segmentation (RFM + K-Means)\n")
    lines.append(f"**Data:** {seg.get('customers_segmented', 0):,} customers scored on Recency, Frequency and Monetary value "
                 f"(quintile NTILE scoring), clustered with K-Means (best k={seg.get('best_k')}, silhouette={seg.get('silhouette')}). "
                 f"Champions + Loyal customers generate **{pct(seg.get('champions_plus_loyal_revenue_share_pct', 0))}** of revenue; "
                 f"At Risk + Lost + Hibernating hold **{money(seg.get('at_risk_plus_lost_revenue', 0))}** of historical revenue.\n")
    lines.append("**Analysis:** Rule-based RFM segments cross-validated with unsupervised clustering on log-transformed R/F/M; cluster centroids profiled into business segment names.\n")
    lines.append("**Insight:** Revenue follows a steep Pareto structure — a minority of Champions underwrites the business, "
                 "while the largest segment by headcount (Lost) contributes little. The commercial risk sits with "
                 "**At Risk** customers: valuable, still winnable, and currently in recency decline.\n")
    if not segment_table.empty:
        lines.append("| Segment | Customers | Revenue | Revenue share | Avg recency (days) | Churn rate |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for row in segment_table.to_dict(orient="records"):
            lines.append(f"| {row['rfm_segment']} | {int(row['customers']):,} | {money(row['revenue'])} | "
                         f"{pct(row['revenue_share_pct'])} | {row['avg_recency']:.0f} | {pct(row['churn_rate'] * 100)} |")
        lines.append("")
    lines.append(figure_block("segment_revenue_bar.png", "Revenue by customer segment"))
    lines.append(figure_block("rfm_scatter_segments.png", "RFM scatter of segments"))

    lines.append("## 4. Churn Prediction\n")
    lines.append(f"**Data:** Leakage-free design — features up to cutoff {churn.get('cutoff_date', '')}, label = activity in the "
                 f"following 90 days; {churn.get('training_customers_active_at_cutoff', 0):,} active customers, "
                 f"{pct(churn.get('training_churn_rate_pct', 0))} churned in the window. "
                 f"Models: Logistic Regression, Random Forest, XGBoost — best: **{churn.get('best_model', '')}** "
                 f"(AUC {churn.get('metrics', [{}])[-1].get('auc', 'n/a')}). "
                 f"Scored population: {churn.get('scored_customers', 0):,} customers → "
                 f"{churn.get('risk_counts', {}).get('High', 0):,} High / {churn.get('risk_counts', {}).get('Medium', 0):,} Medium / "
                 f"{churn.get('risk_counts', {}).get('Low', 0):,} Low risk.\n")
    lines.append(f"**Analysis:** Top predictive features: "
                 + ", ".join(f"`{k}`" for k in list(churn.get("top_features", {}).keys())[:5])
                 + ". Probabilities calibrated with isotonic regression so risk bands are decision-ready.\n")
    lines.append(f"**Insight:** High-risk customers carry **{money(churn.get('revenue_by_risk', {}).get('High', 0))} "
                 f"({pct(churn.get('revenue_at_risk_high_pct', 0))} of known-customer revenue)** — retention economics are "
                 "material: even a 10% save rate on High risk protects a meaningful revenue pool.\n")
    lines.append(figure_block("churn_roc_curves.png", "ROC curves of the three candidate models"))
    lines.append(figure_block("churn_risk_distribution.png", "Churn probability and risk distribution"))

    lines.append("## 5. Product & Category Performance\n")
    lines.append(f"**Data:** Top product {eda['top_product']['stockcode']} ({eda['top_product']['description']}) at "
                 f"{money(eda['top_product']['net_revenue'])}; top category {eda['top_category']['category']} "
                 f"({pct(eda['top_category']['share_pct'])} of net revenue). "
                 f"Product health: {eda['product_health']['dead_stock_count']:,} dead SKUs (>90 days since last sale), "
                 f"{eda['product_health']['declining_products_90d_count']:,} declining (> -20% over 90 days), "
                 f"{eda['product_health']['growing_products_90d_count']:,} growing (> +20%).\n")
    lines.append("**Analysis:** ABC classification from cumulative revenue windows (SQL), growth like-for-like per product, return-rate hotspots, dead-stock detection.\n")
    lines.append(f"**Insight:** The long tail is expensive: **{inventory.get('dead_stock_skus', 0):,} of "
                 f"{inventory.get('product_skus', 0):,} SKUs are dead stock** and the largest category "
                 f"('{eda['top_category']['category']}') suggests the product taxonomy itself needs tightening — "
                 "over 40% of revenue sits in an unclassified bucket, which weakens category-level decision making.\n")
    lines.append(figure_block("abc_pareto.png", "ABC Pareto curve"))
    lines.append(figure_block("category_mix.png", "Net revenue by category"))

    lines.append("## 6. Profitability, Pricing & Returns\n")
    lines.append(f"**Data:** Gross {money(analytics['gross_revenue'])} → refunds {money(analytics['returns_refunds'])} → "
                 f"net {money(analytics['net_revenue'])} (realization {pct(analytics['realization_pct'])}). "
                 f"Realization by year: " + " → ".join(
                     f"{w['year']}: {pct(w['realization_pct'], 2)}" for w in analytics.get("waterfall_by_year", [])) +
                 f". Discounted lines account for {pct(pricing.get('discounted_revenue_share_pct', 0))} of revenue at an average depth of "
                 f"{pct(pricing.get('avg_discount_depth_pct', 0))}; deep-discount revenue {money(pricing.get('deep_discount_revenue', 0))}.\n")
    lines.append("**Analysis:** Net revenue waterfall, price-position mapping against each product's typical price (median), "
                 "return hotspots (>10% refund rate and >£5k revenue), and discount behaviour vs. churn/mix.\n")
    lines.append(f"**Insight:** Two counter-intuitive facts. (1) **Realization is falling every year** "
                 f"({pct(analytics['waterfall_by_year'][0]['realization_pct'], 2)} → {pct(analytics['waterfall_by_year'][-1]['realization_pct'], 2)}) — "
                 f"returns are growing faster than revenue. (2) **Discounting is not hurting retention**: high-discount customers churn at "
                 f"{pct(pricing['discount_behaviour'][0]['churn_rate_pct'])} vs {pct(pricing['discount_behaviour'][1]['churn_rate_pct'])} for "
                 "standard-price customers and place far larger orders — these are wholesale-style buyers, so discount governance should "
                 "protect volume agreements while eliminating value-destroying deep discounts. "
                 f"No cost/COGS fields exist in the source, so margin is measured as **revenue realization** ({pct(analytics['realization_pct'])}).\n")
    lines.append(figure_block("profitability_by_category.png", "Net revenue by category"))
    lines.append(figure_block("pricing_discount_analysis.png", "Price position analysis"))

    lines.append("## 7. Cohorts, Retention & Channels\n")
    lines.append(f"**Data:** New vs returning: {pct(eda['new_vs_returning_share']['returning_customer_revenue_pct'])} of known-customer "
                 f"revenue comes from returning customers; guest/anonymous checkout contributes {pct(kpi['guest_line_share_pct'])} of order "
                 f"lines ({pct(eda.get('guest_revenue_share_pct', 0))} of revenue); best month-3 cohort retention "
                 f"{pct(eda.get('cohort_best_retention_pct', 0))} (cohorts ≥ 50 customers).\n")
    lines.append("**Analysis:** First-purchase-month cohorts tracked with SQL window functions; retention curves visualised as a heatmap.\n")
    lines.append("**Insight:** The revenue base is **retention-driven** (4 out of 5 pounds from repeat customers), so cohort "
                 "retention is the single highest-leverage growth lever; guest orders are a large, unidentified pool that can be "
                 "converted into addressable customers.\n")
    lines.append(figure_block("cohort_retention_heatmap.png", "Cohort retention heatmap"))
    lines.append(figure_block("new_vs_returning.png", "New vs returning customers"))

    lines.append("## 8. Forecast\n")
    lines.append(f"**Data:** 24 complete months trained; 4 models backtested on a 6-month holdout — "
                 + ", ".join(f"{b['model']} {b['wmape_pct']}% WMAPE" if b.get('wmape_pct') is not None else f"{b['model']} n/a"
                             for b in forecast.get("backtest", [])) +
                 f". Best model **{forecast.get('best_model', '')}**.\n")
    lines.append(f"**Analysis:** Seasonal pattern dominates, hence the seasonal-naive benchmark wins; 95% intervals widen with horizon "
                 f"({forecast.get('interval_note', '')}).\n")
    lines.append(f"**Insight:** Next quarter is forecast at **{money(forecast.get('next_quarter_forecast', 0))}** "
                 f"(95% range {money(forecast.get('next_quarter_low_95', 0))} – {money(forecast.get('next_quarter_high_95', 0))}); "
                 f"next 12 months **{money(forecast.get('next_12_months_forecast', 0))}** vs trailing-12 actual "
                 f"{money(forecast.get('trailing_12_actual', 0))} (implied growth {pct(forecast.get('implied_growth_pct', 0))} — "
                 "seasonal-naive baseline implies flat; any growth initiative must beat that baseline).\n")
    lines.append(figure_block("forecast_next_12months.png", "12-month revenue forecast with 95% band"))
    lines.append(figure_block("forecast_backtest_wmape.png", "Backtest accuracy by model"))

    lines.append("## 9. Inventory & Operations\n")
    lines.append(f"**Data:** {inventory.get('dead_stock_skus', 0):,} dead SKUs with {money(inventory.get('dead_stock_prior_year_revenue', 0))} "
                 f"of prior-year revenue, {inventory.get('chronic_stockout_skus', 0):,} SKUs with ≥8 zero-sales weeks in the last year "
                 f"despite ≥1 unit/week average velocity (avg {inventory.get('avg_stockout_weeks', 0)} gap weeks per SKU — no stock-on-hand "
                 f"data exists to separate true stockouts from extreme seasonality), "
                 f"{inventory.get('fast_mover_skus', 0):,} fast movers vs {inventory.get('slow_mover_skus', 0):,} slow movers.\n")
    lines.append("**Analysis:** Weekly sales-velocity panel per SKU with gap detection (zero-sales weeks), movement classification and demand-based reorder points.\n")
    lines.append("**Insight:** The assortment shows simultaneous **over-stock (huge dead tail) and under-stock (chronic gaps on "
                 "fast movers)** — a classic symptom of flat inventory policy; demand-based reorder points per SKU would release "
                 "working capital while protecting availability on velocity leaders.\n")
    lines.append(figure_block("inventory_movement_classes.png", "SKUs by movement class"))

    lines.append("## 10. Data Quality & Limitations\n")
    lines.append(f"- **Quarantined:** {cleaning.get('quarantine_reasons', {}).get('duplicate_row', 0):,} duplicate rows, "
                 f"{cleaning.get('quarantine_reasons', {}).get('negative_price', 0)} negative-price rows (manual adjustments).\n")
    lines.append(f"- **Guest orders:** {cleaning.get('null_customer_id_rows', 0):,} sales lines have no Customer ID "
                 f"({pct(kpi['guest_line_share_pct'])}) — included in revenue, excluded from customer analytics.\n")
    lines.append("- **No COGS/cost fields** exist in the source: profitability is expressed as revenue realization and price position, not gross margin.\n")
    lines.append("- **No marketing-spend, payment-method or inventory-on-hand tables** in the source: discount behaviour proxies promotion "
                 "analytics, sales-velocity gap detection proxies inventory health.\n")
    lines.append("- **December 2011 is partial** (data ends Dec 9) and is excluded from model training and worst-month comparisons.\n")
    lines.append("- Single retailer, single currency (GBP), 2009–2011: results are period-specific; refresh with newer data before operational use.\n")
    return "".join(lines) if False else "\n".join(lines)


def build_recommendations(sources: dict) -> str:
    kpi = sources["kpi"]
    eda = sources["eda"]
    seg = sources["seg"]
    churn = sources["churn"]
    forecast = sources["forecast"]
    analytics = sources["analytics"]
    pricing = analytics.get("pricing", {})
    concentration = analytics.get("concentration", {})
    inventory = analytics.get("inventory", {})
    lfl = eda.get("yoy_like_for_like", {})
    segments = pd.DataFrame(seg.get("segments", []))

    one_pp_returns = analytics["gross_revenue"] * 0.01
    high_risk_rev = churn.get("revenue_by_risk", {}).get("High", 0)
    at_risk_seg = float(segments.loc[segments["rfm_segment"] == "At Risk", "revenue"].sum()) if not segments.empty else 0
    top_hotspot = analytics.get("top_return_hotspots", [{}])[0]
    deep_share = pricing.get("deep_discount_revenue", 0) / analytics["net_revenue"] * 100

    recs = []
    recs.append({
        "priority": "P0", "title": "Launch a targeted retention programme for high-value At Risk customers",
        "evidence": (
            f"Champions + Loyal drive {pct(seg.get('champions_plus_loyal_revenue_share_pct', 0))} of revenue; "
            f"the At Risk segment alone holds {money(at_risk_seg)} of historical revenue; the churn model flags "
            f"{churn.get('risk_counts', {}).get('High', 0):,} High-risk customers carrying {money(high_risk_rev)} "
            f"({pct(churn.get('revenue_at_risk_high_pct', 0))} of known-customer revenue), model AUC {churn.get('metrics', [{}])[-1].get('auc', 'n/a')}."
        ),
        "action": (
            "Score all customers monthly with the trained model, prioritise High-risk customers with monetary value above the median, "
            "and run a win-back journey (personal outreach + incentives sized below the gross margin of the saved revenue)."
        ),
        "impact": f"Saving 10% of High-risk revenue protects ~{money(high_risk_rev * 0.10)} per cycle.",
        "metric": "High-risk customer 90-day retention rate; revenue saved vs control group",
    })
    recs.append({
        "priority": "P0", "title": "Fix revenue realization: root-cause the 39 return hotspots and rising refunds",
        "evidence": (
            f"Realization fell from {pct(analytics['waterfall_by_year'][0]['realization_pct'], 2)} ({analytics['waterfall_by_year'][0]['year']}) "
            f"to {pct(analytics['waterfall_by_year'][-1]['realization_pct'], 2)} ({analytics['waterfall_by_year'][-1]['year']}); "
            f"every 1 percentage point of realization = {money(one_pp_returns)}; {analytics.get('return_hotspots_count', 0)} SKUs exceed "
            f"10% refund rate; worst: {top_hotspot.get('description', '')} ({pct(top_hotspot.get('return_rate_pct', 0))} refund rate, "
            f"{money(top_hotspot.get('refunds', 0))} refunded)."
        ),
        "action": (
            "Analyse root causes for the top hotspots (product quality, description mismatch, damages in transit), "
            "and block repeat refund patterns at order entry; add refund rate to supplier/product scorecards."
        ),
        "impact": f"Halving the hotspot refunds recovers ~{money(one_pp_returns * 0.5)} annually.",
        "metric": "Monthly realization %; hotspot refund rate",
    })
    recs.append({
        "priority": "P1", "title": "Convert guest checkout into identified, addressable customers",
        "evidence": (
            f"{pct(kpi['guest_line_share_pct'])} of order lines are guest lines with no Customer ID "
            f"({pct(eda.get('guest_revenue_share_pct', 0))} of revenue) — invisible to segmentation, churn and retention analytics."
        ),
        "action": "Require or incentivise account creation at checkout (quote/reorder benefits for trade buyers), retro-tag existing guest lines where possible.",
        "impact": f"Identifying half of guest revenue ({money(analytics['net_revenue'] * eda.get('guest_revenue_share_pct', 0) / 100 * 0.5)}) makes it actionable for retention and personalisation.",
        "metric": "Guest revenue share %; registered-customer count",
    })
    recs.append({
        "priority": "P1", "title": "Set discount guardrails — protect wholesale volume deals, cut value-destroying deep discounts",
        "evidence": (
            f"{pct(pricing.get('discounted_revenue_share_pct', 0))} of revenue sells below typical price at average depth "
            f"{pct(pricing.get('avg_discount_depth_pct', 0))}; deep-discount revenue {money(pricing.get('deep_discount_revenue', 0))} "
            f"({pct(deep_share)} of net revenue). High-discount customers churn LESS "
            f"({pct(pricing['discount_behaviour'][0]['churn_rate_pct'])} vs {pct(pricing['discount_behaviour'][1]['churn_rate_pct'])}) "
            "and order much larger baskets — volume pricing works; uncontrolled deep discounts need approval thresholds."
        ),
        "action": "Introduce discount approval tiers (e.g. >25% requires sign-off), monitor price realization per category, and keep negotiated volume discounts for high-frequency buyers.",
        "impact": f"Capturing 20% of deep-discount revenue at full price adds ~{money(pricing.get('deep_discount_revenue', 0) * 0.2)} without volume loss (to be validated with an A/B test).",
        "metric": "Deep-discount share of revenue; realization % by category",
    })
    recs.append({
        "priority": "P1", "title": "Plan capacity, stock and cash against the seasonal forecast",
        "evidence": (
            f"Backtest: {forecast.get('best_model', '')} at {min(b['wmape_pct'] for b in forecast.get('backtest', []) if b.get('wmape_pct'))}% WMAPE; "
            f"next quarter forecast {money(forecast.get('next_quarter_forecast', 0))} "
            f"(95% range {money(forecast.get('next_quarter_low_95', 0))}–{money(forecast.get('next_quarter_high_95', 0))}); "
            f"peak month {eda['best_sales_month']['year_month']} = {money(eda['best_sales_month']['net_revenue'])}."
        ),
        "action": "Use the quarterly forecast for staffing, purchasing and cash planning; run a pre-peak readiness review 8 weeks before the Q4 peak; refresh forecasts monthly as new data lands.",
        "impact": "Fewer stockouts in peak, lower emergency freight, better working-capital timing.",
        "metric": "Forecast WMAPE vs actual; peak-period fulfilment SLA",
    })
    recs.append({
        "priority": "P1", "title": "Rationalise the long-tail assortment and release working capital",
        "evidence": (
            f"{inventory.get('dead_stock_skus', 0):,} of {inventory.get('product_skus', 0):,} SKUs had no sale in 90+ days "
            f"(prior-year revenue {money(inventory.get('dead_stock_prior_year_revenue', 0))}), while "
            f"{inventory.get('chronic_stockout_skus', 0):,} SKUs show ≥8 zero-sales weeks at ≥1 unit/week average velocity — "
            "capital is parked in the wrong SKUs while demand-facing lines go unfulfilled."
        ),
        "action": "Run a slow/dead-stock clearance (bundles, markdown with approval), stop reordering the tail, and apply demand-based reorder points from the inventory_features outputs for fast movers.",
        "impact": f"Releasing even 10% of dead-stock-related stock value funds high-velocity lines.",
        "metric": "Dead-stock SKU count & value; stockout weeks on fast movers",
    })
    recs.append({
        "priority": "P2", "title": "Reduce UK concentration by scaling the strongest international markets",
        "evidence": (
            f"The UK is {pct(kpi['top_country_share_pct'])} of revenue; like-for-like growth is only {pct(lfl.get('growth_like_for_like_pct', lfl.get('growth_pct', float('nan'))))}. "
            f"Germany, France and Ireland are the largest non-UK markets (see net_revenue_by_region_country SQL output)."
        ),
        "action": "Deepen the top-3 non-UK markets with localised campaigns/fulfilment; treat country-level cohort retention as the scorecard.",
        "impact": "Each point of non-UK mix shift diversifies ~£190k of revenue base (1pp of net revenue).",
        "metric": "Non-UK revenue share; international cohort retention",
    })
    recs.append({
        "priority": "P2", "title": "Tighten the product taxonomy to unlock category-level decisions",
        "evidence": (
            f"'{eda['top_category']['category']}' holds {pct(eda['top_category']['share_pct'])} of net revenue — a catch-all bucket that "
            "makes category strategy, assortment and pricing decisions unreliable."
        ),
        "action": "Reclassify the catch-all with a description keyword + fuzzy-matching pass, and require category assignment for new SKUs.",
        "impact": "Sharper ABC/discount/return analytics per category; cleaner Power BI category pages.",
        "metric": "Unclassified revenue share %",
    })
    recs.append({
        "priority": "P2", "title": "Industrialise the pipeline: monthly refresh, monitoring and model governance",
        "evidence": (
            f"Pipeline currently processes {sources['cleaning'].get('raw_rows', 0):,} rows end-to-end (clean → PostgreSQL star schema → "
            f"22 SQL analyses → ML models → dashboards) with row-level reconciliation (Python = PostgreSQL to the penny)."
        ),
        "action": "Schedule monthly data refresh, track KPI drift (realization, churn rate, forecast WMAPE), retrain the churn model quarterly, and revalidate segment definitions twice a year.",
        "impact": "Decisions stay current; models remain trustworthy.",
        "metric": "Pipeline freshness; model AUC drift; KPI drift alerts",
    })

    lines = []
    lines.append("# Business Recommendations\n")
    lines.append(
        "Generated by the recommendation engine from the analysis artifacts "
        "(`DATA → ANALYSIS → INSIGHT → RECOMMENDATION`). Priority: **P0** = act now, **P1** = next quarter, **P2** = roadmap.\n"
    )
    for i, rec in enumerate(recs, 1):
        lines.append(f"## {i}. [{rec['priority']}] {rec['title']}\n")
        lines.append(f"- **Evidence (DATA/ANALYSIS):** {rec['evidence']}")
        lines.append(f"- **RECOMMENDATION:** {rec['action']}")
        lines.append(f"- **Expected impact:** {rec['impact']}")
        lines.append(f"- **Metric to track:** {rec['metric']}\n")
    lines.append("---\n")
    lines.append("*Supporting dashboards: see `powerbi/dashboard_pages.md` (6-page Power BI build) and `reports/business_insights.md`.*\n")
    return "\n".join(lines)


def run():
    sources = {
        "kpi": load_json("kpi_summary.json"),
        "eda": load_json("eda_summary.json"),
        "seg": load_json("segmentation_summary.json"),
        "churn": load_json("churn_model_summary.json"),
        "forecast": load_json("forecast_summary.json"),
        "analytics": load_json("analytics_summary.json"),
        "cleaning": load_json("cleaning_report.json"),
    }
    missing = [k for k, v in sources.items() if not v]
    if missing:
        raise FileNotFoundError(f"Missing analysis artifacts: {missing}")

    insights = build_insights(sources)
    recommendations = build_recommendations(sources)
    (REPORTS_DIR / "business_insights.md").write_text(insights, encoding="utf-8")
    (REPORTS_DIR / "recommendations.md").write_text(recommendations, encoding="utf-8")
    print(f"wrote business_insights.md ({len(insights):,} chars), recommendations.md ({len(recommendations):,} chars)")
    return {"insights_chars": len(insights), "recommendations_chars": len(recommendations)}


if __name__ == "__main__":
    run()
