# Power BI — Executive Sales Dashboard

Build assets for the Power BI Desktop report over the `enterprise_sales` star schema (UCI Online Retail II, 2009-12-01 → 2011-12-09, GBP).

| File | Purpose |
|---|---|
| `README.md` | This guide — data export, connection, refresh, tips |
| `data_model.md` | Star schema ER diagram, relationships, flat report tables |
| `measures.dax` | 41 measures in 6 sections — paste into `_Measures` |
| `dashboard_pages.md` | Page-by-page build instructions for the 6 report pages |

---

## 1. Export the data

From the repository root:

```
python src\export_powerbi.py
```

Outputs:

| Location | Files |
|---|---|
| `data\processed\powerbi\` | `fact_sales.csv`, `fact_returns.csv`, `dim_date.csv`, `dim_product.csv`, `dim_customer.csv`, `dim_country.csv` |
| `data\processed\powerbi\` | `customer_insights.csv`, `forecast_monthly.csv`, `model_metrics.csv`, `monthly_series.csv`, `cohort_retention.csv`, `product_features.csv`, `inventory_features.csv` |
| `data\processed\sql_results\` | `monthly_revenue_trend.csv`, `mom_yoy_growth.csv`, `rolling_averages_daily.csv`, `rfm_segmentation_sql.csv`, `cohort_retention.csv`, `customer_lifetime_value.csv`, `category_performance.csv`, `revenue_waterfall.csv`, `net_revenue_by_region_country.csv`, … (optional reference visuals) |
| `data\processed\` | `kpi_summary.json` — validation KPIs |

Never hand-edit these files; re-run the export instead.

## 2. Connection: Import from CSV (recommended)

**Recommendation: Import mode from the CSV exports.** The model is 1.01 M fact rows — well within Import limits — and Import gives fast DAX, full time intelligence, and no dependency on a running PostgreSQL instance. DirectQuery only makes sense if the database changes constantly and you cannot accept a refresh cycle.

| | Import from CSV (recommended) | PostgreSQL DirectQuery | PostgreSQL Import |
|---|---|---|---|
| Source | Flat files | `localhost:5432`, database `enterprise_sales`, user `postgres` | Live DB, loaded into the model |
| Speed | In-memory, instant interactions | Every interaction hits the DB; slowest on this row count | Same as CSV Import after load |
| Time intelligence | Full DAX (`SAMEPERIODLASTYEAR`, `DATESINPERIOD`, …) | Supported but query-bound | Full DAX |
| Offline / portability | Works without any DB | Requires running DB + driver | Requires DB at refresh time only |
| Refresh | Home → Refresh (re-reads CSVs) | Always live | Home → Refresh |

**PostgreSQL path (alternative):** Get data → *PostgreSQL database* → Server `localhost:5432`, Database `enterprise_sales` → choose **Import** (or DirectQuery if required) → sign in (User `postgres`, Windows/SQL auth as configured).

## 3. Import the CSVs

1. Home → **Get data → Text/CSV** → select a file → **Transform Data**.
2. In Power Query set types, then **Close & Apply**. Repeat for all files above.

   | Tables | Columns to set |
   |---|---|
   | `dim_date` | `full_date`, `week_starting` → **Date**; `is_weekend`, `is_month_start`, `is_month_end` → **True/False**; keys/ints → **Whole Number** |
   | `dim_product` | `is_service` → **True/False**; `typical_price` → **Decimal Number**; `launch_date`, `discontinued_date` → **Date** |
   | `dim_customer` | `customer_key`, `customer_id`, `country_key`, `orders`, `tenure_days` → **Whole Number**; `first_order_date`, `last_order_date` → **Date**; money columns → **Decimal Number** |
   | `dim_country` | `country_key` → **Whole Number** |
   | `fact_sales`, `fact_returns` | `date_key`, `customer_key`, `product_key`, `country_key`, `quantity` → **Whole Number**; `unit_price`, `line_revenue`, `refund_amount` → **Decimal Number**; `line_id`/`return_id` → **Whole Number** |
   | Flat tables | `forecast_month` → **Date**; numeric fractions (`churn_probability`, `return_rate`, `growth_90d_pct`, retention columns `0`–`12`) stay **Decimal Number**; `churned_actual` → **Whole Number** |

   CSV booleans arrive as `TRUE`/`FALSE` and auto-detect as True/False.
3. `kpi_summary.json`: Get data → **JSON** → select the file → right-click the *Record* → **Convert to Table** → *Expand All* columns → Load (single-row reference table).
4. `sql_results\*.csv`: optional; import for reference visuals only — they are pre-aggregated snapshots and do not respond to slicers.

## 4. Verify relationships

Model view must show exactly the 8 relationships from `data_model.md` §1 — all **many-to-one**, all **Single** direction, `dim_country` **not** connected to `dim_customer`. Fix any both-direction arrows (they cause ambiguous filters). Optionally add the four flat-table relationships listed in `data_model.md` §2 for slicer interactivity.

## 5. Create the measures

1. Home → **Enter data** → name the table `_Measures` → add a placeholder column `id` (value `1`) → Load. Hide `id` (Column tools → **Hide**); the table becomes the measure container.
2. Load the measures:
   - **Single:** Home → *New measure* → paste one measure from `measures.dax` (including its `Name =` line) → Enter. Repeat for all 41.
   - **Batch (faster):** install Tabular Editor 2 → open the model → right-click `_Measures` → paste the full contents of `measures.dax` → **Save** (writes back into the .pbix).
3. Apply format strings per the `// Format:` comments above each measure (Measure tools → Format): `£#,##0` / `£#,##0.00` for money, `0.0%` for shares, `#,##0` for counts.

## 6. Build the report

Follow `dashboard_pages.md` in order: conventions → pages 1–6 → navigation/bookmarks → tooltips → validation checklist against `kpi_summary.json`.

## 7. Page navigation (report tabs)

| # | Page tab | Purpose |
|---|---|---|
| 1 | Executive Overview | KPIs vs PY, trend + forecast, region/category mix, guest share |
| 2 | Sales Analytics | YoY/MoM momentum, rolling average, top products, heatmap, segments |
| 3 | Customer Intelligence | RFM matrix, churn risk, revenue at risk, Pareto, cohort retention |
| 4 | Product & Profitability | Category economics, ABC Pareto, top/bottom SKUs, price position, dead stock |
| 5 | Returns & Pricing | Refund trend, hotspots, price position by category, refund rate by country |
| 6 | Forecast & Risk | Actual vs forecast band, model metrics, inventory and customer risk |

## 8. Refresh

- **Desktop:** Home → **Refresh** re-reads the CSVs (run `python src\export_powerbi.py` first). Use *Data source settings* if files move.
- **Published (Power BI Service):** local CSV paths need an **on-premises data gateway**; or move `data\processed\powerbi\` to OneDrive/SharePoint, repoint sources, and schedule refresh without a gateway. PostgreSQL DirectQuery also requires a gateway for cloud access.

## 9. Tips

- **Hide helper columns:** hide surrogate keys in Report view — `line_id`, `return_id`, `date_key` (facts and `dim_date`), `customer_key`, `product_key`, `country_key`. Keep them in the model (relationships need them).
- **Data categories:** `dim_country[country]` and `dim_customer[country]` → *Data category* = **Country** (enables Map/Filled map). Do this before building page 2.
- **Currency:** format every money measure `£#,##0` (cards) or `£#,##0.00` (AOV); for columns use *Currency → £, English (United Kingdom)*. Negative values red via `£#,##0;[Red]-£#,##0`.
- **Mark the Date table:** right-click `dim_date` → **Mark as date table** → Date column `full_date`. Also File → Options → Current File → Data Load → disable *Auto date/time* (the model has its own date dimension).
- **Sort labels:** `dim_date[day_name]` → Sort by `day_of_week`; `dim_date[month_name]` → Sort by `month` (Data view → Column tools → Sort by column).
- **Name collisions:** `[Orders]`, `[AOV]`, `[Units]` are measures; qualify columns when needed (e.g. `'monthly_series'[orders]`).
- **Do not build visuals on `data\processed\pg_load\`** — those are load artefacts of the same tables; use the `powerbi` exports.
- **Performance:** keep `Customer Cumulative Share %` on tables of ≤ 100 rows; prefer visual *Top N* filters over ranking full tables.

## Advanced Dashboard Recommendations
- **KPI Cards**: Total Revenue, Net Revenue, Orders, AOV, Active Customers, Churn Rate, Returns %
- **Trend Analysis**: Monthly/Quarterly revenue trends with YoY comparison and growth %
- **Geographic Performance**: Revenue by Country/Region with drill-through
- **Customer Intelligence**: RFM segments, CLTV, Churn risk distribution
- **Product Analytics**: Top products by revenue, ABC classification, return hotspots
- **Forecasting & Risk**: 12-month forecast with confidence bands, revenue at risk by segment
