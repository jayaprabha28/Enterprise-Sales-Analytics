"""Generate the 5 runnable .ipynb notebooks from the pipeline modules."""
import nbformat as nbf

from config import NOTEBOOKS_DIR

NBFORMAT_VERSION = 4


def md(text: str) -> dict:
    return nbf.v4.new_markdown_cell(source=text)


def code(src: str) -> dict:
    return nbf.v4.new_code_cell(source=src)


def nb(title: str, cells: list) -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook(cells=cells)
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.14"},
    }
    return nb


def figures(captions: list) -> list:
    out = []
    for name, note in captions:
        out.append(md(f"### Figure\n`{name}`\n\n_{note}_"))
        out.append(code(
            "from IPython.display import Image, display\n"
            "from config import FIGURES_DIR\n"
            f"display(Image(filename=str(FIGURES_DIR / {name!r})))\n"
        ))
    return out


def build_data_cleaning():
    cells = [
        md("""# 01 — Data Cleaning & Reconciliation

**Dataset:** UCI Online Retail II (Kaggle) — 1,067,371 raw transaction lines
(`data/raw/online_retail_ii.csv`). This notebook reproduces every cleaning step in
`src/data_cleaning.py` and reconciles the output against the raw file.

Business rules applied:
- drop rows with unparseable invoice dates;
- quarantine exact duplicate rows, null quantities/prices, negative prices, zero quantities;
- classify service stock codes (`POST`, `M`, `BANK CHARGES`, `GIFT`, `GIFT_*`, ...) as `is_service`;
- fill missing descriptions with the modal description of the stock code;
- map countries → regions (`UK / Europe / Americas / Asia Pacific / Middle East & Africa / Unknown`);
- split positive/non-credit-note lines into `fact_sales` and credit-note/negative-qty lines into `fact_returns`."""),
        code(
            "import sys\n"
            "sys.path.insert(0, r\"../src\")\n"
            "import pandas as pd\n"
            "import data_cleaning\n"
            "from config import RAW_CSV\n"
        ),
        code("df = data_cleaning.load_raw()\n" "print(df.shape)\n" "df.head()"),
        md("## Step 1 — anomalies in the raw extract"),
        code(
            "print('bad dates        :', df['invoice_date'].isna().sum())\n"
            "print('null descriptions:', df['description'].isna().sum())\n"
            "print('null customer id :', df['customer_id'].isna().sum())\n"
            "print('null price/qty   :', (df['unit_price'].isna() | df['quantity'].isna()).sum())\n"
            "print('negative price   :', (df['unit_price'] < 0).sum())\n"
            "print('zero qty         :', (df['quantity'] == 0).sum())\n"
            "print('duplicate rows   :', df.duplicated(keep='first').sum())\n"
            "print('negative qty     :', (df['quantity'] < 0).sum())\n"
            "print('credit notes     :', df['invoice'].str.startswith('C', na=False).sum())\n"
            "print('countries        :', df['country'].nunique())"
        ),
        md("## Step 2 — cleaning, splitting, reconciliation"),
        code(
            "fact_sales, fact_returns, quarantine, report = data_cleaning.clean(df)\n"
            "print('sales rows  :', len(fact_sales))\n"
            "print('return rows :', len(fact_returns))\n"
            "print('quarantined :', len(quarantine))\n"
            "print('reconciled  :', report['reconciled'])"
        ),
        md("## Step 3 — persist and verify against human-readable checks"),
        code(
            "data_cleaning.write_outputs(fact_sales, fact_returns, quarantine, report)\n"
            "print({k: report[k] for k in ['gross_sales_revenue', 'returns_refunds', 'net_revenue', 'distinct_invoices', 'distinct_customers', 'distinct_products']})"
        ),
        md("## Step 4 — first look at the cleaned facts"),
        code(
            "fact_sales.groupby('country')['line_revenue'].sum().nlargest(10).to_frame().style.format({'line_revenue': '£{:,.0f}'})"
        ),
        md("""**Result:** 1,010,534 sales lines + 22,497 return lines + 34,340 quarantined =
1,067,371 raw rows (reconciled). Full report in `data/processed/cleaning_report.json`.

The **same cleaned frames** are loaded into PostgreSQL in step 03 (see `src/load_postgres.py`)."""),
    ]
    return nb("01_data_cleaning", cells)


def build_eda():
    cells = [
        md("""# 02 — Exploratory Data Analysis (EDA)

Regenerates the 12 `reports/figures/*.png` charts and `data/processed/eda_summary.json`
produced by `src/eda.py`, then walks through the headline findings."""),
        code(
            "import sys\n"
            "sys.path.insert(0, r\"../src\")\n"
            "from pathlib import Path\n"
            "import json\n"
            "import eda\n"
            "from config import FIGURES_DIR\n"
        ),
        md("## Step 1 — regenerate analytics & figures"),
        code("summary = eda.run()\n" "print(json.dumps(summary, indent=2))"),
        md("## Step 2 — revenue & seasonality"),
        *figures([
            ("revenue_trend_monthly.png", "Monthly gross vs net revenue (Nov-09 peak)."),
            ("revenue_yoy_compare.png", "2010 vs 2011 monthly comparison (like-for-like)."),
            ("top_countries.png", "Net revenue by country — UK dominates."),
            ("weekday_pattern.png", "Order volume by weekday."),
        ]),
        md("## Step 3 — customers, products, cohorts"),
        *figures([
            ("customer_recency_frequency.png", "Customer recency vs frequency scatter."),
            ("category_mix.png", "Net revenue by product category."),
            ("cohort_retention_heatmap.png", "Cohort retention heatmap."),
            ("new_vs_returning.png", "New vs returning customers by month."),
        ]),
        md("""**Headline findings** (full detail in `data/processed/eda_summary.json`):
- Best month **2011-11 £1,456,145.80**; YoY like-for-like **+1.8%**;
- Churn rate (90-day) **50.9%**; top product `22423 REGENCY CAKESTAND`;
- AOV mean **£488**, median **£291**; guests = **15% of revenue**;
- **1,640 dead SKUs** (>90 days since last sale)."""),
    ]
    return nb("02_eda", cells)


def build_segmentation():
    cells = [
        md("""# 03 — Customer Segmentation (RFM + K-Means)

Recreates `src/segmentation.py`: NTILE R/F/M scores → rule-based RFM segments,
then K-Means clustering on a signed-log transform of (recency, frequency, monetary)
with silhouette-based model selection (best k=2). Outputs:

- `data/processed/customer_segments.parquet|csv` — per-customer scores & segments;
- `data/processed/segment_stats.csv`, `segmentation_summary.json`; figures in `reports/figures/`."""),
        code(
            "import sys\n"
            "sys.path.insert(0, r\"../src\")\n"
            "from pathlib import Path\n"
            "import json\n"
            "import pandas as pd\n"
            "from IPython.display import Image, display\n"
            "import segmentation\n"
            "from config import FIGURES_DIR, PROCESSED_DIR\n"
        ),
        md("## Step 1 — run the module end-to-end"),
        code("summary = segmentation.run()\n" "print(json.dumps({k: v for k, v in summary.items() if k != 'segments'}, indent=2))"),
        md("## Step 2 — segment economics table"),
        code(
            "pd.read_csv(PROCESSED_DIR / 'segment_stats.csv').sort_values('revenue', ascending=False).style.format({\n"
            "    'revenue': '£{:,.0f}', 'avg_recency': '{:.0f}', 'churn_rate': '{:.0%}'})"
        ),
        md("## Step 3 — the segment view"),
        *figures([
            ("segment_revenue_bar.png", "Revenue by customer segment."),
            ("rfm_scatter_segments.png", "K-Means clusters on R/F/M space."),
            ("segment_rfm_heatmap.png", "RFM score profile per segment."),
            ("kmeans_selection.png", "Silhouette vs k — model selection."),
        ]),
        md("""**Result:** Champions+Loyal customers = **80.4% of revenue** while the *Lost* segment is the
largest by count — retention is the dominant value lever (feeds the churn model in 04)."""),
    ]
    return nb("03_customer_segmentation", cells)


def build_churn():
    cells = [
        md("""# 04 — Churn Prediction

Recreates `src/churn_model.py`. Design is **leakage-free**:
features are built only from data up to `cutoff = snapshot − 90d` (2011-09-10);
eligible = recency ≤ 180 days at cutoff; label = any purchase in the following 90 days.

Three models are compared (Logistic Regression, Random Forest, XGBoost) and the best is
re-fitted with **isotonic calibration** so `churn_probability` and the
High/Medium/Low risk bands are decision-ready (thresholds from `config.RISK_THRESHOLDS`)."""),
        code(
            "import sys\n"
            "sys.path.insert(0, r\"../src\")\n"
            "import json\n"
            "import pandas as pd\n"
            "from IPython.display import Image, display\n"
            "import churn_model\n"
            "from config import FIGURES_DIR, PROCESSED_DIR\n"
        ),
        md("## Step 1 — train, calibrate and score"),
        code("churn_model.run()\n" "print(json.dumps(json.load(open(PROCESSED_DIR / 'churn_model_summary.json')), indent=2))"),
        md("## Step 2 — model metrics"),
        code("pd.read_csv(PROCESSED_DIR / 'model_metrics.csv').style.format({'auc': '{:.4f}', 'accuracy': '{:.3f}', 'precision': '{:.3f}', 'recall': '{:.3f}', 'f1': '{:.3f}'})"),
        md("## Step 3 — risk distribution & diagnostics"),
        *figures([
            ("churn_roc_curves.png", "ROC curves, three models + calibrated best."),
            ("churn_confusion_matrix.png", "Calibrated model on holdout."),
            ("churn_feature_importance.png", "Top predictive features."),
            ("churn_risk_distribution.png", "Scored probability distribution with risk bands."),
        ]),
        md("""**Result:** Best model **Logistic Regression**, AUC **0.768**. High-risk customers number **2,495**
and carry **£1.53M (9.3%) of known-customer revenue** — the retention target for recommendations.""")
    ]
    return nb("04_churn_prediction", cells)


def build_forecast():
    cells = [
        md("""# 05 — Sales Forecasting

Recreates `src/forecasting.py`. Monthly net revenue series (2010-01 … 2011-11; 2011-12 is
partial → excluded from training) is rolled forward on a 6-month holdout for
**Moving Average, Holt (Brown), Holt-Winters (additive) and Seasonal Naive**.
Best backtest model → point forecast 2011-12…2012-11 plus a ±95% band."""),
        code(
            "import sys\n"
            "sys.path.insert(0, r\"../src\")\n"
            "import json\n"
            "import pandas as pd\n"
            "from IPython.display import Image, display\n"
            "import forecasting\n"
            "from config import FIGURES_DIR, PROCESSED_DIR\n"
        ),
        md("## Step 1 — backtest + forecast"),
        code("forecasting.run()\n" "print(json.dumps(json.load(open(PROCESSED_DIR / 'forecast_summary.json')), indent=2, default=str))"),
        md("## Step 2 — model comparison (WMAPE on holdout)"),
        code("pd.read_csv(PROCESSED_DIR / 'forecast_monthly.csv').pipe(lambda d: d[d['backtest_wmape_pct'].notna()])[['model', 'backtest_wmape_pct']].drop_duplicates().sort_values('backtest_wmape_pct')"),
        md("## Step 3 — the forecast"),
        *figures([
            ("forecast_next_12months.png", "12-month forecast with 95% band."),
            ("forecast_backtest_wmape.png", "Backtest accuracy by model."),
            ("forecast_model_comparison.png", "Model fit vs actuals."),
        ]),
        md("""**Result:** **Seasonal Naive** wins the backtest at **6.1% WMAPE** (the series is dominated by
seasonality). Next quarter ≈ **£1,802,198** (range £1,288k–£2,316k); next 12 months ≈ **£9.32M** — flat vs
trailing 12 months, i.e. any real growth must come from the recommendations, not from the baseline."""),
    ]
    return nb("05_sales_forecasting", cells)


def run():
    books = [
        build_data_cleaning(),
        build_eda(),
        build_segmentation(),
        build_churn(),
        build_forecast(),
    ]
    names = [
        "01_data_cleaning.ipynb",
        "02_exploratory_analysis.ipynb",
        "03_customer_segmentation.ipynb",
        "04_churn_prediction.ipynb",
        "05_sales_forecasting.ipynb",
    ]
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    for book, name in zip(books, names):
        path = NOTEBOOKS_DIR / name
        nbf.write(book, path)
        print(f"wrote {path.relative_to(NOTEBOOKS_DIR.parents[1])} ({len(book['cells'])} cells)")
    return {"notebooks": len(names)}


if __name__ == "__main__":
    run()