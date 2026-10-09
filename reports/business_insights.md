# Business Insights — Enterprise Sales & Revenue Intelligence Platform

**Source data:** UCI Online Retail II (Kaggle) — 1,067,371 raw transaction lines (2009-12-01 to 2011-12-09), cleaned to 1,010,534 sales lines + 22,497 credit lines with 34,340 rows quarantined (duplicate_row: 34335, negative_price: 5). Currency: GBP. Business snapshot: 2011-12-09.

## 1. Executive Summary

| KPI | Value |
|---|---|
| Gross revenue | £20,476,260 |
| Returns & refunds | £1,462,051 (7.1% of gross) |
| Net revenue | £19,014,210 |
| Orders | 41,938 |
| Average order value | £453 |
| Registered customers | 5,881 |
| Products (non-service) | 4,793 across 43 countries |
| YoY like-for-like growth (Jan–Dec 9) | 1.8% |
| Churned customers (90-day) | 50.9% |
| UK revenue concentration | 85.0% |

The business is a **large, UK-dominated wholesale-style operation**: 85.0% of revenue comes from the United Kingdom, the top 1% of customers generate 31.0% of known-customer revenue, and average order value of £453 indicates trade/wholesale order patterns rather than consumer retail. Growth is modest but positive on a like-for-like basis, while **revenue realization is eroding** (returns rising year over year) and **half the customer base is churned** on a 90-day definition.

## 2. Revenue & Growth

**Data:** Best trading month 2011-11 at £1,456,146; worst complete month 2011-04 at £492,368. Like-for-like (Jan 1–Dec 9): £8,845,679 in 2010 → £9,001,425 in 2011.

**Analysis:** Monthly revenue decomposed into trend, seasonality and year-over-year comparisons using window functions (SQL) and Python time-series aggregation.

**Insight:** Revenue is **strongly seasonal with a Q4 (Christmas) peak** — the strongest month runs at roughly 3x the weakest complete month — and like-for-like growth is **1.8%**, i.e. the business is growing slowly while facing increasing returns.

![Monthly gross vs net revenue](figures/revenue_trend_monthly.png)

*Monthly gross vs net revenue*
![2010 vs 2011 monthly comparison](figures/revenue_yoy_compare.png)

*2010 vs 2011 monthly comparison*
![Revenue by country](figures/top_countries.png)

*Revenue by country*
## 3. Customer Segmentation (RFM + K-Means)

**Data:** 5,881 customers scored on Recency, Frequency and Monetary value (quintile NTILE scoring), clustered with K-Means (best k=2, silhouette=0.4323). Champions + Loyal customers generate **80.4%** of revenue; At Risk + Lost + Hibernating hold **£2,166,473** of historical revenue.

**Analysis:** Rule-based RFM segments cross-validated with unsupervised clustering on log-transformed R/F/M; cluster centroids profiled into business segment names.

**Insight:** Revenue follows a steep Pareto structure — a minority of Champions underwrites the business, while the largest segment by headcount (Lost) contributes little. The commercial risk sits with **At Risk** customers: valuable, still winnable, and currently in recency decline.

| Segment | Customers | Revenue | Revenue share | Avg recency (days) | Churn rate |
|---|---:|---:|---:|---:|---:|
| Champions | 1,261 | £11,322,462 | 69.2% | 19 | 0.0% |
| Loyal Customers | 698 | £1,820,398 | 11.1% | 85 | 40.5% |
| At Risk | 858 | £1,596,108 | 9.8% | 374 | 100.0% |
| Big Spenders | 218 | £445,310 | 2.7% | 67 | 26.1% |
| New Customers | 598 | £383,971 | 2.4% | 34 | 0.0% |
| Lost | 1,517 | £365,169 | 2.2% | 453 | 100.0% |
| Potential Loyalists | 349 | £212,426 | 1.3% | 28 | 0.0% |
| Hibernating | 382 | £205,196 | 1.2% | 117 | 72.3% |

![Revenue by customer segment](figures/segment_revenue_bar.png)

*Revenue by customer segment*
![RFM scatter of segments](figures/rfm_scatter_segments.png)

*RFM scatter of segments*
## 4. Churn Prediction

**Data:** Leakage-free design — features up to cutoff 2011-09-10, label = activity in the following 90 days; 2,787 active customers, 38.2% churned in the window. Models: Logistic Regression, Random Forest, XGBoost — best: **Logistic Regression + isotonic calibration** (AUC 0.7697). Scored population: 5,881 customers → 2,495 High / 1,862 Medium / 1,524 Low risk.

**Analysis:** Top predictive features: `purchase_days`, `frequency`, `avg_price_paid`, `monetary`, `distinct_products`. Probabilities calibrated with isotonic regression so risk bands are decision-ready.

**Insight:** High-risk customers carry **£1,528,568 (9.3% of known-customer revenue)** — retention economics are material: even a 10% save rate on High risk protects a meaningful revenue pool.

![ROC curves of the three candidate models](figures/churn_roc_curves.png)

*ROC curves of the three candidate models*
![Churn probability and risk distribution](figures/churn_risk_distribution.png)

*Churn probability and risk distribution*
## 5. Product & Category Performance

**Data:** Top product 22423 (REGENCY CAKESTAND 3 TIER) at £314,045; top category Other Products (40.6% of net revenue). Product health: 1,640 dead SKUs (>90 days since last sale), 842 declining (> -20% over 90 days), 1,699 growing (> +20%).

**Analysis:** ABC classification from cumulative revenue windows (SQL), growth like-for-like per product, return-rate hotspots, dead-stock detection.

**Insight:** The long tail is expensive: **1,628 of 4,793 SKUs are dead stock** and the largest category ('Other Products') suggests the product taxonomy itself needs tightening — over 40% of revenue sits in an unclassified bucket, which weakens category-level decision making.

![ABC Pareto curve](figures/abc_pareto.png)

*ABC Pareto curve*
![Net revenue by category](figures/category_mix.png)

*Net revenue by category*
## 6. Profitability, Pricing & Returns

**Data:** Gross £20,476,260 → refunds £1,462,051 → net £19,014,210 (realization 92.9%). Realization by year: 2009: 96.86% → 2010: 93.73% → 2011: 91.66%. Discounted lines account for 35.2% of revenue at an average depth of 31.4%; deep-discount revenue £1,224,001.

**Analysis:** Net revenue waterfall, price-position mapping against each product's typical price (median), return hotspots (>10% refund rate and >£5k revenue), and discount behaviour vs. churn/mix.

**Insight:** Two counter-intuitive facts. (1) **Realization is falling every year** (96.86% → 91.66%) — returns are growing faster than revenue. (2) **Discounting is not hurting retention**: high-discount customers churn at 40.5% vs 53.0% for standard-price customers and place far larger orders — these are wholesale-style buyers, so discount governance should protect volume agreements while eliminating value-destroying deep discounts. No cost/COGS fields exist in the source, so margin is measured as **revenue realization** (92.9%).

![Net revenue by category](figures/profitability_by_category.png)

*Net revenue by category*
![Price position analysis](figures/pricing_discount_analysis.png)

*Price position analysis*
## 7. Cohorts, Retention & Channels

**Data:** New vs returning: 82.6% of known-customer revenue comes from returning customers; guest/anonymous checkout contributes 22.9% of order lines (15.2% of revenue); best month-3 cohort retention 42.5% (cohorts ≥ 50 customers).

**Analysis:** First-purchase-month cohorts tracked with SQL window functions; retention curves visualised as a heatmap.

**Insight:** The revenue base is **retention-driven** (4 out of 5 pounds from repeat customers), so cohort retention is the single highest-leverage growth lever; guest orders are a large, unidentified pool that can be converted into addressable customers.

![Cohort retention heatmap](figures/cohort_retention_heatmap.png)

*Cohort retention heatmap*
![New vs returning customers](figures/new_vs_returning.png)

*New vs returning customers*
## 8. Forecast

**Data:** 24 complete months trained; 4 models backtested on a 6-month holdout — Moving Average 32.47% WMAPE, Seasonal Naive 6.08% WMAPE, Holt 25.18% WMAPE, Holt-Winters n/a. Best model **Seasonal Naive**.

**Analysis:** Seasonal pattern dominates, hence the seasonal-naive benchmark wins; 95% intervals widen with horizon (Approximate 95% bands from residual volatility (ETS bands widen with horizon)).

**Insight:** Next quarter is forecast at **£1,802,199** (95% range £1,287,952 – £2,316,446); next 12 months **£9,315,430** vs trailing-12 actual £9,315,430 (implied growth 0.0% — seasonal-naive baseline implies flat; any growth initiative must beat that baseline).

![12-month revenue forecast with 95% band](figures/forecast_next_12months.png)

*12-month revenue forecast with 95% band*
![Backtest accuracy by model](figures/forecast_backtest_wmape.png)

*Backtest accuracy by model*
## 9. Inventory & Operations

**Data:** 1,628 dead SKUs with £1,685,339 of prior-year revenue, 2,168 SKUs with ≥8 zero-sales weeks in the last year despite ≥1 unit/week average velocity (avg 27.7 gap weeks per SKU — no stock-on-hand data exists to separate true stockouts from extreme seasonality), 633 fast movers vs 634 slow movers.

**Analysis:** Weekly sales-velocity panel per SKU with gap detection (zero-sales weeks), movement classification and demand-based reorder points.

**Insight:** The assortment shows simultaneous **over-stock (huge dead tail) and under-stock (chronic gaps on fast movers)** — a classic symptom of flat inventory policy; demand-based reorder points per SKU would release working capital while protecting availability on velocity leaders.

![SKUs by movement class](figures/inventory_movement_classes.png)

*SKUs by movement class*
## 10. Data Quality & Limitations

- **Quarantined:** 34,335 duplicate rows, 5 negative-price rows (manual adjustments).

- **Guest orders:** 231,039 sales lines have no Customer ID (22.9%) — included in revenue, excluded from customer analytics.

- **No COGS/cost fields** exist in the source: profitability is expressed as revenue realization and price position, not gross margin.

- **No marketing-spend, payment-method or inventory-on-hand tables** in the source: discount behaviour proxies promotion analytics, sales-velocity gap detection proxies inventory health.

- **December 2011 is partial** (data ends Dec 9) and is excluded from model training and worst-month comparisons.

- Single retailer, single currency (GBP), 2009–2011: results are period-specific; refresh with newer data before operational use.
