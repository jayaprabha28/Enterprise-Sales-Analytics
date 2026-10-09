# Enterprise Sales Analytics — Python → PostgreSQL → Power BI

An end-to-end revenue intelligence platform built on the real Kaggle dataset
**[UCI Online Retail II](https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci)** —
1,067,371 transaction lines from a UK-based wholesale/retail e-commerce business
(Dec 2009 → Dec 2011, GBP). The pipeline takes the raw CSV through a reproducible
cleaning stage into a PostgreSQL **star schema**, runs **22 SQL analyses**, then trains
**customer segmentation, churn prediction and forecasting** models and exports
**Power BI-ready flat files** plus auto-generated business reports.

```
raw CSV ──▶ data_cleaning ──▶ fact_sales / fact_returns / quarantine (parquet)
                 │
                 ▼
          feature_engineering ──▶ dimensions, customer/product features, monthly series
                 │
                 ▼
          load_postgres ──▶ PostgreSQL star schema (COPY loader, row-reconciled)
                 │
                 ▼
          run_sql ──▶ 22 analytics queries → data/processed/sql_results/*.csv
                 │
                 ▼
   eda ─▶ segmentation ─▶ churn_model ─▶ forecasting ─▶ analytics
                 │                                                  │
                 ▼                                                  ▼
     reports/figures/*.png  ◀───────────────       recommendation_engine
                 ▼                                        │
          export_powerbi ──▶ data/processed/powerbi/*.csv  ▼
                 │                          reports/*.md, notebooks/*.ipynb
                 ▼
        Power BI Desktop (see powerbi/)
```

---

## Key results (from the current run)

| Area | Result |
|---|---|
| Extracted & cleansed | 1,067,371 raw → 1,010,534 sales + 22,497 returns + 34,340 quarantined, **reconciled to the row** |
| Integrated | Star schema in PostgreSQL 18 — **Python = Postgres to the penny** (`matches_python: true`) |
| SQL analytics | 22 queries across sales, customers, products, profitability |
| EDA | 12 figures; best month Nov-2011 £1,456k; YoY like-for-like **+1.8%**; churn **50.9%**; 1,640 dead SKUs |
| Segmentation | RFM (+K-Means, silhouette 0.43); **Champions+Loyal = 80.4% of revenue** |
| Churn | Best model **Logistic Regression AUC 0.768** (isotonic-calibrated); 2,495 High-risk customers = **£1.53M** revenue at risk |
| Forecast | **Seasonal Naive, 6.1% WMAPE** backtest; next quarter **£1.80M** (95% band £1.29–2.32M); next 12m **£9.32M** |
| Business story | `reports/business_insights.md`, `reports/recommendations.md` (P0/P1/P2), 6-page Power BI build |

---

## Repository layout

```
├── data/
│   ├── raw/                 # online_retail_ii.csv (download, see below)
│   └── processed/           # parquet, csv, summary json, sql_results/, powerbi/
├── sql/
│   ├── schema.sql           # star schema DDL
│   └── *_analysis.sql       # 22 analytics queries
├── src/
│   ├── config.py            # paths, DB config, business rules
│   ├── data_cleaning.py     # raw → facts + quarantine + reconciliation
│   ├── feature_engineering.py # dims, features, monthly/weekly series, cohorts, KPI json
│   ├── load_postgres.py     # CREATE SCHEMA + COPY loader + revenue cross-check
│   ├── run_sql.py           # executes the 22 queries → sql_results/*.csv
│   ├── eda.py               # 12 figures + eda_summary.json
│   ├── segmentation.py      # RFM + K-Means customer segmentation
│   ├── churn_model.py       # leakage-free churn model + isotonic calibration
│   ├── forecasting.py       # backtest + 12-month forecast
│   ├── analytics.py         # profitability, pricing/discount, inventory, returns
│   ├── recommendation_engine.py # builds business_insights.md + recommendations.md
│   ├── export_powerbi.py    # star + flat CSVs for Power BI
│   ├── build_notebooks.py   # generates the 5 .ipynb
│   └── run_all.py           # one-command end-to-end pipeline
├── notebooks/               # 5 runnable Jupyter notebooks (jupyter nbconvert --execute)
├── powerbi/                 # README, data model, 41 DAX measures, 6 dashboard pages
├── reports/
│   ├── figures/             # all charts
│   └── business_insights.md, recommendations.md
├── requirements.txt
└── LICENSE
```

---

## Setup

### 1. Python

```bash
python -m pip install -r requirements.txt
```

### 2. PostgreSQL (18)

Install PostgreSQL, then make local-host auth trust-based so the loader can connect:

```powershell
# edit %PROGRAMDATA%\PostgreSQL\18\data\pg_hba.conf :
#   change the IPv4 local lines from scram-sha-256/md5 to trust, restart the service
```

`schema.sql` and `load_postgres.py` create the `enterprise_sales` database and tables
and `COPY`-load the data on first run. Table creation is idempotent.

### 3. Data

Place `online_retail_ii.csv` in `data/raw/` (or run
`LoadFile -Path https://www.kaggle.com/api/v1/datasets/download/mashlyn/online-retail-ii-uci -DestinationPath data/raw/online_retail_ii.zip`
and unzip). The pipeline errors with a clear message if the file is missing.

---

## Run the whole pipeline

```bash
python src\run_all.py          # everything, in dependency order
```

...or step by step (each script is independently rerunnable/idempotent):

```bash
python src\data_cleaning.py    # clean → parquet facts + cleaning_report.json
python src\feature_engineering.py
python src\load_postgres.py    # requires PostgreSQL running
python src\run_sql.py          # 22 SQL analyses → data/processed/sql_results/
python src\eda.py
python src\segmentation.py
python src\churn_model.py
python src\forecasting.py
python src\analytics.py
python src\recommendation_engine.py   # reports/*.md
python src\export_powerbi.py          # data/processed/powerbi/*.csv
python src\build_notebooks.py         # notebooks/*.ipynb (execute with jupyter)
```

---

## Validation philosophy

- Row-level reconciliation: `sales + returns + quarantine + dropped = raw` (`reconciled: true`).
- Cross-system check: PostgreSQL `SUM(line_revenue)` == Python aggregate **to the penny**
  (`load_postgres.py` prints `matches_python: true`).
- Churn model is leakage-free (cutoff = snapshot − 90d; features ≤ cutoff; label = next 90d)
  and calibrated so risk bands are decision-ready.
- Forecast is backtested on a held-out 6 months with WMAPE, with the partial last month excluded.

## Known data limitations (also in `reports/business_insights.md` §10)

- No cost/COGS or inventory-on-hand fields → profitability is **revenue realization**
  (net of refunds) and price position; inventory health uses sales-velocity gap detection.
- No marketing-spend/salesperson tables → discount analytics and customer analytics substitute.
- Guest lines (no Customer ID, ~23% of lines) are revenue-inclusive but customer-excluded.
- December 2011 is partial (data ends Dec 9) — excluded from model training.

---

## Power BI

`powerbi/README.md` is the complete rebuild guide: CSV import (recommended) or PostgreSQL
DirectQuery, the 8 relationships, 41 DAX measures, and the 6-page dashboard spec
(Executive Overview, Sales, Customer Intelligence, Product & Profitability, Returns & Pricing,
Forecast & Risk). Exports live in `data/processed/powerbi/`.

## ML Evaluation & Data Integrity
- **Churn Model**: Leakage-free design (features up to cutoff, label = next 90 days). Evaluated with Accuracy, Precision, Recall, F1, ROC-AUC.
- **Forecasting**: Multiple models compared (Moving Average, Seasonal Naive, Holt, Holt-Winters), backtested with time-based validation. Metrics tracked include WMAPE, MAE, RMSE.
- **Data Leakage Prevention**: Cutoff-based temporal validation ensures no future information leaks into training features.
- **Reconciliation**: Sales + Returns + Quarantine + Dropped = Raw; PostgreSQL revenue cross-checks against Python aggregates to the penny.

## MongoDB Integration (Optional)
MongoDB can be enabled as a NoSQL complement to PostgreSQL for storing pipeline logs, data quality results, customer insights, model predictions, and recommendation logs.

**Setup:**
1. Set environment variables (or use .env.example as template):
`ash
MONGODB_ENABLED=true
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=enterprise_sales_analytics
`
2. Install dependencies: pip install -r requirements.txt (includes pymongo)
3. Run sync: python src/mongo_integration.py

**Collections:** pipeline_runs, data_quality_results, customer_insights, model_predictions, recommendation_logs

**Note:** PostgreSQL remains the primary analytics database. MongoDB integration is optional, can be disabled via config, and failures never interrupt the core pipeline.

## License

MIT — see `LICENSE`. Dataset © its Kaggle owner / original authors (research use).