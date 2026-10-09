# Dashboard Pages — Executive Report Build Guide

Exact build instructions for the 6-page executive dashboard in Power BI Desktop. Complete `README.md` (connection + measures) first, then build pages in order. Page tab names below are the exact names to use.

Measures referenced as `[Name]` live in `_Measures` (from `measures.dax`). Field references are `table[column]`.

---

## 0. Report conventions

| Item | Setting |
|---|---|
| Canvas | 16:9, zoom Fit to page |
| Navigation | Button bar on **every** page (see §7) |
| Global slicer panel | Right edge, 220 px wide, top-to-bottom: **Date Range**, **Region**, **Category** (see §7) |
| Tooltip page | Page `Tooltip – Trend`, 320×240, *Page information → Use as tooltip* (see §8) |
| Colours | Net revenue `#1F6FEB`, refunds `#D13438`, forecast `#FFB900`, prior year `#8A8A8A`, positive `#107C10`, negative `#D13438` |
| Currency | All £ measures formatted per `measures.dax` comments |

**Global slicers (add once per page, sync across pages: View → Sync slicers):**

1. **Date Range** — Slicer, *Between* type, field `dim_date[full_date]` (2009-12-01 → 2011-12-09).
2. **Region** — Slicer, Dropdown, field `dim_country[region]` (transaction geography; includes guest lines).
3. **Category** — Slicer, Dropdown, field `dim_product[category]`.

Pages built on disconnected flat tables do not respond to these slicers unless the optional relationships from `data_model.md` §2 were created — each visual below notes the behaviour.

---

## 1. Executive Overview

**Purpose:** one-screen health check: headline KPIs vs prior year, revenue trajectory with forecast, geographic and category mix, guest contribution.

| # | Visual (type) | Fields | Measures & configuration |
|---|---|---|---|
| 1 | KPI card — Net Revenue (Card, new) | Callout: `[Net Revenue]` | Reference label: `[PY Net Revenue]`. Below it a text card: `[Net Revenue vs PY Indicator]` with fx rules on `[YoY Growth %]`: ≥ 0 → `#107C10`, < 0 → `#D13438` |
| 2 | KPI card — AOV (Card, new) | Callout: `[AOV]` | Reference label: quick measure *Value previous year* on `[AOV]`. fx colour rules on the quick measure: ≥ 0 green, < 0 red |
| 3 | KPI card — Orders (Card, new) | Callout: `[Orders]` | Reference label: quick measure *Value previous year* on `[Orders]`; same fx rules |
| 4 | KPI card — Active Customers (Card, new) | Callout: `[Active Customers]` | Reference label: quick measure *Value previous year* on `[Active Customers]`; same fx rules |
| 5 | KPI card — Return Rate % (Card, new) | Callout: `[Return Rate %]` | Reference label: quick measure *Value previous year* on `[Return Rate %]`. **Invert colours** (lower is better): < PY → green, ≥ PY → red |
| 6 | Monthly net revenue trend with forecast (Line chart) | Axis: `forecast_monthly[forecast_month]` (continuous date); Values: `forecast_monthly[actual_net_revenue]` renamed *Actual*, `forecast_monthly[forecast_net_revenue]` renamed *Forecast* | Visual-level filter: `forecast_monthly[model]` = "Seasonal Naive". Forecast: `#FFB900` dashed; Actual: `#1F6FEB`. Confidence band: Format → *Error bars* on the Forecast series, Upper = `upper_95`, Lower = `lower_95` — or plot `lower_95`/`upper_95` as thin semi-transparent grey lines. Requires the optional `forecast_monthly → dim_date` relationship for the date slicer to apply (otherwise full series) |
| 7 | Net revenue by region (Clustered bar) | Axis: `dim_country[region]`; Values: `[Net Revenue]` | Sort descending; data labels on, `£#,##0`; click-to-filter enabled (default) |
| 8 | Net revenue by category (Treemap) | Group: `dim_product[category]`; Values: `[Net Revenue]` | Top 8 categories shown, rest under *Show items with no data* off; tooltip: `[Return Rate %]` |
| 9 | Guest vs registered revenue (Donut) | Values: `[Guest Net Revenue]`, `[Registered Net Revenue]`; no legend | Rename series *Guest* / *Registered*; data labels percentage + category. If only one slice renders, use a clustered bar with the same two measures instead. Tooltip: `[Guest Revenue %]` |

**Slicers:** global panel (Date Range, Region, Category) — visuals 7, 8 respond; 6 and 9 only if optional relationships exist (9 otherwise shows totals).
**Conditional formatting:** KPI fx rules above; card callout values £-formatted.
**Bookmarks/interactions:** `Reset slicers` bookmark button (§7); Edit interactions → card row does not cross-filter the charts (cards visual → Filter icon off).

---

## 2. Sales Analytics

**Purpose:** trend anatomy — YoY/MoM momentum, rolling average, product and geography leaders, weekly seasonality, customer segment contribution.

| # | Visual (type) | Fields | Measures & configuration |
|---|---|---|---|
| 1 | Monthly trend with YoY (Line chart) | Axis: `dim_date[year_month]` (text sorts chronologically); Values: `[Net Revenue]`, `[PY Net Revenue]` | PY line grey `#8A8A8A` dashed; Revenue `#1F6FEB`. Blank PY on 2009-12 is expected. Tooltip: `[MoM Growth %]`, `[Orders]` |
| 2 | YoY / MoM growth (Clustered column) | Axis: `dim_date[year_month]`; Values: `[YoY Growth %]`, `[MoM Growth %]` | Data labels on, format `0.0%;-0.0%`; YoY `#1F6FEB`, MoM `#8A8A8A`; secondary axis off (both %) |
| 3 | Rolling 30-day revenue (Line chart) | Axis: `dim_date[full_date]` (continuous); Values: `[Net Revenue]` (thin, grey), `[Rolling 30-Day Net Revenue]` (thick, `#1F6FEB`) | Add Analytics → Average line optional; tooltip: `[Orders]`, `[AOV]` |
| 4 | Top 10 products (Table) | Columns: `dim_product[stockcode]`, `dim_product[description]`, `[Net Revenue]`, `[Units]`, `[Return Rate %]` | Visual filter → Top 10 by `[Net Revenue]`; fx **data bars** on `[Net Revenue]`; fx **colour scale** on `[Return Rate %]` (white → red); sort by `[Net Revenue]` desc |
| 5 | Revenue by country (Map, or clustered bar fallback) | Location: `dim_country[country]` (Data category = Country); Size: `[Net Revenue]`; Legend: `dim_country[region]` | Map needs internet; otherwise clustered bar, Axis `dim_country[country]`, Top 10 by `[Net Revenue]` |
| 6 | Weekday × month heatmap (Matrix) | Rows: `dim_date[day_name]`; Columns: `dim_date[month_name]`; Values: `[Net Revenue]` | **Sort setup (Data view):** `day_name` → Sort by column `day_of_week`; `month_name` → Sort by column `month`. fx **background colour scale** on `[Net Revenue]` (white → `#1F6FEB`), no data labels |
| 7 | Customer segment revenue (Clustered bar) — *replaces the salesperson view: no salesperson data exists* | Axis: `customer_insights[kmeans_segment]`; Values: `Sum of customer_insights[monetary]` (implicit) | Sort desc; tooltip columns `rfm_segment` not applicable — tooltip: count of `customer_id`. Uses the customer flat table: responds to `dim_customer` slicers only if the optional relationship exists; otherwise it is a fixed full-period view |

**Slicers:** global panel (visuals 1–6 respond; 7 per note).
**Conditional formatting:** data bars + colour scales as listed; negative % labels show with minus sign.
**Interactions:** visual 1 cross-filters 2 and 3 (date axis shared); visual 4 cross-filters 5 and 6.

---

## 3. Customer Intelligence

**Purpose:** who the customers are — RFM segments, churn risk, revenue concentration (Pareto), cohort retention, acquisition mix.

| # | Visual (type) | Fields | Measures & configuration |
|---|---|---|---|
| 1 | RFM segment matrix (Matrix) | Rows: `customer_insights[rfm_segment]`; Values: `Count of customer_id`, `Sum of monetary` | Sort rows by `Sum of monetary` desc (click header). fx **data bars** on Sum of monetary; format £ |
| 2 | Churn risk donut (Donut) | Legend: `customer_insights[risk_level]`; Values: `Count of customer_id` | Manual colours: High `#D13438`, Medium `#FFB900`, Low `#107C10`; labels: percentage + category |
| 3 | Risk cards (3 × Card, new) | `[Revenue at Risk]` (£, fx colour red), `[Churn Rate %]` (0.0%), `[Churned Customers]` (#,##0) | Reference labels: none; tooltip on Churn Rate: `Count of customer_id` |
| 4 | Top customers Pareto (Table) | Columns: `customer_insights[customer_id]`, `customer_insights[country]`, `Sum of monetary`, `[Customer Revenue Rank]`, `[Customer Cumulative Share %]` | Visual filter → Top 50 by `Sum of monetary`; sort desc; fx data bars on Sum of monetary; cumulative column format 0.0%. Lighter alternative: quick measure *Cumulative value* on Sum of monetary (By: `customer_id`) + *Percent of grand total* |
| 5 | Cohort retention heatmap (Matrix) | Rows: `cohort_retention[cohort_month]`; Values: columns `0` … `12` (all 13 retention-fraction fields) | Values format `0%`; fx **background colour scale** 0 → 1 (white → `#107C10`); no grand totals. Optional long-format build: Power Query → select `0`…`12` → *Unpivot other columns*, rename `Attribute` → `month_index`, `Value` → `retention`; then Rows `cohort_month`, Columns `month_index`, Values `retention` |
| 6 | New vs returning customers (Line chart) | Axis: `monthly_series[year_month]`; Values: `Sum of monthly_series[new_customers]`, `Sum of monthly_series[returning_customers]` | Stacked area or clustered line; flat table → ignores the date slicer (full series); tooltip: `Sum of monthly_series[active_customers]` |

**Slicers:** global panel (nothing on this page responds unless optional relationships exist) **plus a local slicer** `customer_insights[region]` (dropdown) so this page is filterable in the spec model. If the optional `customer_insights → dim_customer` relationship exists, switch the local slicer to `dim_customer[region]`.
**Conditional formatting:** data bars (1, 4), colour scale (5), manual donut colours (2), red card (3).
**Bookmarks:** none beyond global.

---

## 4. Product & Profitability

**Purpose:** which products make money — category economics, ABC concentration, leaders/laggards, price position, dead stock.

| # | Visual (type) | Fields | Measures & configuration |
|---|---|---|---|
| 1 | Category revenue vs return rate (Scatter/Bubble) | X axis: `[Net Revenue]`; Y axis: `[Return Rate %]`; Legend: `dim_product[category]`; Size: `[Orders]` | Tooltip: `[Units]`, `[Category Net Revenue]`; bubble transparency 30%; Add analytic line (trend) optional. Both facts filter through `dim_product`, so Y is category-consistent |
| 2 | ABC Pareto combo (Line and clustered column) | Axis: `product_features[abc_class]` (sorts A→B→C as text); Columns: `Sum of product_features[gross_revenue]`; Line: quick measure *Cumulative value* (Base: Sum of gross_revenue, By: `abc_class`) on secondary axis | Columns `#1F6FEB`, line `#FFB900`; data labels on; tooltip: `[ABC A Revenue Share]`. Requires optional `product_features → dim_product` relationship for the category slicer |
| 3 | Top 10 / Bottom 10 products (2 × Table) | Columns: `dim_product[stockcode]`, `dim_product[description]`, `dim_product[category]`, `[Net Revenue]`, `[Units]`, `[Return Rate %]` | Table A: Top 10 by `[Net Revenue]`; Table B: Bottom 10 by `[Net Revenue]` (filter → *Bottom* toggle). Data bars on `[Net Revenue]` |
| 4 | Price position share (100% stacked bar, single bar) | Values: `[Above-Median Price Revenue Share]`, `[Below-Median Price Revenue Share]` | Data labels `0%`; colours `#1F6FEB` / `#8A8A8A`; tooltip: `[Avg Unit Price]` |
| 5 | Dead stock table (Table) | Columns: `inventory_features[stockcode]`, `inventory_features[description]`, `inventory_features[category]`, `inventory_features[days_since_last_sale]`, `inventory_features[avg_weekly_units]`, `inventory_features[reorder_point_units]` | Visual filter: `inventory_features[movement_class]` = "Dead Stock"; fx colour scale on `days_since_last_sale` (light → dark red); companion card: `[Dead Stock SKUs]` |

**Slicers:** global panel (1, 3 respond; 2 and 5 need optional relationships).
**Conditional formatting:** data bars (3), colour scale (5), share colours (4).

---

## 5. Returns & Pricing

**Purpose:** where refunds hurt — trend, hotspots, price positioning, country return rates.

| # | Visual (type) | Fields | Measures & configuration |
|---|---|---|---|
| 1 | Refund trend (Line chart) | Axis: `dim_date[year_month]`; Values: `[Total Refunds]` | Line `#D13438`; add second line `[Return Rate %]` on secondary axis (`0.0%`); tooltip: `[Gross Revenue]` |
| 2 | Return hotspots (Matrix) | Rows: `dim_product[category]`; Columns: `dim_country[region]`; Values: `[Total Refunds]` | fx background colour scale (white → `#D13438`); values format `£#,##0`; sort rows by total desc; row subtotals on |
| 3 | Price position by category (100% stacked bar) | Axis: `dim_product[category]`; Values: `[Above-Median Price Revenue Share]`, `[Below-Median Price Revenue Share]` | Sort by above-median share desc; labels `0%`; colours `#1F6FEB` / `#8A8A8A` |
| 4 | Refund rate by country (Clustered bar) | Axis: `dim_country[country]` (Top 15 by `[Total Refunds]`); Values: `[Return Rate %]` | fx **rules** on bar colours: ≥ 10% `#D13438`, 5–10% `#FFB900`, < 5% `#107C10`; data labels `0.00%`; tooltip: `[Total Refunds]`, `[Net Revenue]` |
| 5 | Returns KPI strip (2 × Card) | `[Total Refunds]` (£), `[Return Rate %]` (0.00%) | Reference label on Refunds: none; card colour red-tinted |

**Slicers:** global panel — all star-schema visuals respond (both facts share `dim_date`/`dim_product`/`dim_country`).
**Conditional formatting:** colour scales (2), rules (4).

---

## 6. Forecast & Risk

**Purpose:** forward view — actual vs forecast with confidence band, model quality, inventory risk, customer risk summary.

| # | Visual (type) | Fields | Measures & configuration |
|---|---|---|---|
| 1 | Actual vs forecast with 95% band (Line chart) | Axis: `forecast_monthly[forecast_month]`; Values: `actual_net_revenue` (*Actual*), `forecast_net_revenue` (*Forecast*), `lower_95` (*Lower 95%*), `upper_95` (*Upper 95%*) | Visual filter: `forecast_monthly[model]` = "Seasonal Naive". Actual `#1F6FEB` solid; Forecast `#FFB900` dashed; bounds thin grey dashed — or Format → Error bars on Forecast (Upper = `upper_95`, Lower = `lower_95`) with 60% transparency. Legend bottom; tooltip: all four values |
| 2 | Model comparison (Table) | Columns: `model_metrics[model]`, `model_metrics[auc]`, `model_metrics[accuracy]`, `model_metrics[precision]`, `model_metrics[recall]`, `model_metrics[f1]` | Format `0.000`; fx colour scale on `auc` (red → green); sort by `auc` desc |
| 3 | Inventory risk cards (2 × Card, new) | `[Dead Stock SKUs]` (#,##0), `[SKUs with Stockouts (52w)]` (#,##0) | Card colours: dead stock red-tint, stockout amber-tint |
| 4 | Movement class profile (Clustered bar) | Axis: `inventory_features[movement_class]`; Values: `Count of stockcode` | Manual colours: Dead Stock `#D13438`, Slow Mover `#FFB900`, Normal `#8A8A8A`, Fast Mover `#107C10`, Service `#1F6FEB`; sort by count desc; tooltip: `Sum of inventory_features[units_sold]` |
| 5 | Risk summary (3 × Card + text card) | `[Revenue at Risk]` (£, red), `[Churn Rate %]` (0.0%), `[Forecast Net Revenue (Next Month)]` (£), text: `[Forecast Accuracy Note]` | Forecast card reference labels: `[Forecast Low (Next Month)]` / `[Forecast High (Next Month)]` (use two reference labels or a second card) |
| 6 | Forecast next-month range (Card trio, optional) | `[Forecast Low (Next Month)]`, `[Forecast Net Revenue (Next Month)]`, `[Forecast High (Next Month)]` | Shows the 95% interval as Low / Expected / High |

**Slicers:** global panel — visuals 2–4 respond only via optional relationships; 1 and 5/6 anchor on `MAX('dim_date'[full_date])`, so they follow the date slicer's upper bound when the optional `forecast_monthly → dim_date` relationship exists (otherwise they always use 2011-12-09 → next month 2011-12).
**Conditional formatting:** rules on model table; manual movement-class colours.

---

## 7. Navigation, slicers, bookmarks

**Button navigation (every page):**

1. Insert → Buttons → Blank × 6, aligned top-left, labelled: `Executive Overview`, `Sales Analytics`, `Customer Intelligence`, `Product & Profitability`, `Returns & Pricing`, `Forecast & Risk`.
2. Each button: Action → On → Type **Page navigation** → Target = matching page.
3. Format the active page's button with the accent fill; copy/paste the strip onto each page (actions persist).

**Slicer panel (every page):** insert the three slicers from §0 in a right-hand panel, title them, and use View → **Sync slicers** so all pages share state.

**Bookmarks:**

| Bookmark | Purpose | Setup |
|---|---|---|
| `Reset slicers` | Clear all slicers to default | Clear the three slicers on any page → View → Bookmarks → Add → rename `Reset slicers` → uncheck *Display*, keep **Data** + *Current page* → assign to a `Reset` button (Action → Bookmark) |
| `Executive only` (optional) | Hide detail visuals on page 1 | Selection pane → hide visuals → Bookmarks → Add → *Selected visuals* only |

After editing visuals, right-click the bookmark → **Update**.

---

## 8. Tooltips page

1. New page → rename `Tooltip – Trend` → Page format → Canvas size → Type **Tooltip** (320×240) → Page information → **Use as tooltip** = On.
2. Add a small line chart: Axis `dim_date[full_date]`, Values `[Rolling 30-Day Net Revenue]` and `[Net Revenue]`; title off; no slicers.
3. On target visuals: Format → General → Tooltips → Type **Page** → Page = `Tooltip – Trend`.
4. Apply to the KPI cards (page 1), trend visuals (pages 1–2), and hotspot table (page 5).

---

## 9. Validation checklist (after building)

Compare cards against `data/processed/kpi_summary.json` with slicers cleared:

| KPI | Expected |
|---|---|
| `[Gross Revenue]` | £20,476,260.43 |
| `[Total Refunds]` | £1,462,050.61 |
| `[Net Revenue]` | £19,014,209.82 |
| `[Orders]` | 41,938 |
| `[Active Customers]` | 5,881 |
| `[AOV]` | £453.39 |
| `[Return Rate %]` | 7.14% |
| `[YoY Growth %]` (2011 partial vs 2010) | ≈ −2.3% |
| `[Guest Revenue %]` / guest line share | ≈ 23% of lines |
| `[Churn Rate %]` | 50.9% |
| `[Top Country Revenue Share %]` | ≈ 85.0% |
| `[Dead Stock SKUs]` | 1,640 |
| `[Products with Returns Over 10%]` | non-zero; `product_features[return_rate]` is 0–1 |
| Rows: `fact_sales` / `fact_returns` | 1,010,534 / 22,497 |

Any mismatch → check relationship directions (all Single), guest NULL keys not filtered out, and that `dim_date` is marked as the Date table.
