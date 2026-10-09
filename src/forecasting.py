"""Revenue forecasting: Moving Average, Seasonal Naive, Holt and Holt-Winters with rolling backtest."""
import json
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from statsmodels.tsa.holtwinters import ExponentialSmoothing, Holt

from config import FIGURES_DIR, PROCESSED_DIR

MODEL_NAMES = ["Moving Average", "Seasonal Naive", "Holt", "Holt-Winters"]


def load_series():
    monthly = pd.read_parquet(PROCESSED_DIR / "monthly_series.parquet")
    monthly["period"] = pd.to_datetime(monthly["year_month"] + "-01")
    kpis = json.loads((PROCESSED_DIR / "kpi_summary.json").read_text())
    snapshot = pd.Timestamp(kpis["snapshot_date"])
    complete = monthly[monthly["period"] + pd.offsets.MonthEnd(0) <= snapshot].copy()
    partial = monthly[monthly["period"] + pd.offsets.MonthEnd(0) > snapshot].copy()
    series = complete.set_index("period")["net_revenue"].sort_index()
    partial_actual = partial.set_index("period")["net_revenue"].to_dict()
    return series, partial_actual


def forecast_moving_average(train: pd.Series, horizon: int, window: int = 3):
    value = float(train.tail(window).mean())
    forecast = np.full(horizon, value)
    residuals = train - train.rolling(window).mean()
    sigma = float(residuals.dropna().std())
    return forecast, sigma


def forecast_seasonal_naive(train: pd.Series, horizon: int):
    index = pd.date_range(train.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    forecast = np.array([train.asfreq("MS").get(ts - pd.DateOffset(years=1), np.nan) for ts in index])
    if np.isnan(forecast).any():
        forecast = np.where(np.isnan(forecast), train.iloc[-12:].mean(), forecast)
    aligned = train - train.shift(12)
    sigma = float(aligned.dropna().std())
    return forecast, sigma, index


def forecast_ets(model_name: str, train: pd.Series, horizon: int):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if model_name == "Holt":
            fitted = Holt(train, damped_trend=False, initialization_method="estimated").fit(optimized=True)
        else:
            fitted = ExponentialSmoothing(
                train, trend="add", seasonal="add", seasonal_periods=12, initialization_method="estimated"
            ).fit(optimized=True)
        values = np.asarray(fitted.forecast(horizon), dtype=float)
    sigma = float(np.std(fitted.resid.dropna(), ddof=1))
    spread = 1.96 * sigma * np.sqrt(np.arange(1, horizon + 1))
    return values, values - spread, values + spread


def build_forecast(model_name: str, train: pd.Series, horizon: int, index: pd.DatetimeIndex):
    if model_name == "Moving Average":
        values, sigma = forecast_moving_average(train, horizon)
        return values, values - 1.96 * sigma, values + 1.96 * sigma
    if model_name == "Seasonal Naive":
        values, sigma, index = forecast_seasonal_naive(train, horizon)
        return values, values - 1.96 * sigma, values + 1.96 * sigma
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        values, lower, upper = forecast_ets(model_name, train, horizon)
    return values, lower, upper


def backtest(series: pd.Series, holdout: int = 6):
    train, test = series.iloc[:-holdout], series.iloc[-holdout:]
    index = test.index
    results = []
    for name in MODEL_NAMES:
        try:
            values, _, _ = build_forecast(name, train, holdout, index)
            values = np.asarray(values, dtype=float)
            errors = test.to_numpy() - values
            mape = float(np.mean(np.abs(errors) / test.to_numpy()) * 100)
            mae = float(np.mean(np.abs(errors)))
            wmape = float(np.sum(np.abs(errors)) / np.sum(np.abs(test.to_numpy())) * 100)
            results.append({"model": name, "mape_pct": round(mape, 2), "mae": round(mae, 2), "wmape_pct": round(wmape, 2), "status": "ok"})
        except Exception as exc:
            results.append({"model": name, "mape_pct": None, "mae": None, "wmape_pct": None, "status": f"failed: {exc}"})
    return pd.DataFrame(results)


def run():
    series, partial_actual = load_series()
    horizon = 12
    future_index = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    snapshot = series.index[-1] + pd.offsets.MonthEnd(0)

    backtest_df = backtest(series, holdout=6)
    valid = backtest_df[backtest_df["wmape_pct"].notna()]
    best_model = valid.loc[valid["wmape_pct"].idxmin(), "model"] if len(valid) else "Holt-Winters"

    rows = []
    for name in MODEL_NAMES:
        values, lower, upper = build_forecast(name, series, horizon, future_index)
        values = np.asarray(values, dtype=float)
        lower = np.asarray(lower, dtype=float)
        upper = np.asarray(upper, dtype=float)
        wmape = backtest_df.loc[backtest_df["model"] == name, "wmape_pct"].iloc[0]
        for i, ts in enumerate(future_index):
            actual = None
            if ts in series.index:
                actual = float(series.loc[ts])
            elif ts in partial_actual:
                actual = float(partial_actual[ts])
            rows.append({
                "forecast_month": ts.strftime("%Y-%m-%d"),
                "model": name,
                "forecast_net_revenue": round(float(values[i]), 2),
                "lower_95": round(float(lower[i]), 2),
                "upper_95": round(float(upper[i]), 2),
                "actual_net_revenue": round(actual, 2) if actual is not None else None,
                "actual_is_partial": bool(ts in partial_actual),
                "backtest_wmape_pct": wmape,
                "is_best_model": bool(name == best_model),
            })
    forecast_df = pd.DataFrame(rows)

    best_rows = forecast_df[forecast_df["model"] == best_model].set_index("forecast_month")
    next_quarter = best_rows.head(3)
    next_6 = best_rows.head(6)
    next_12 = best_rows
    trailing_12 = float(series.tail(12).sum())
    forecast_12_total = float(next_12["forecast_net_revenue"].sum())

    summary = {
        "training_months": int(len(series)),
        "training_window": f"{series.index[0].date()} to {series.index[-1].date()}",
        "data_note": "2011-12 excluded from training (only 9 days of data); shown as partial actual in charts",
        "interval_note": "Approximate 95% bands from residual volatility (ETS bands widen with horizon)",
        "models_compared": MODEL_NAMES,
        "backtest": backtest_df.astype(object).where(backtest_df.notna(), None).to_dict(orient="records"),
        "best_model": best_model,
        "next_quarter_forecast": round(float(next_quarter["forecast_net_revenue"].sum()), 2),
        "next_quarter_low_95": round(float(next_quarter["lower_95"].sum()), 2),
        "next_quarter_high_95": round(float(next_quarter["upper_95"].sum()), 2),
        "next_6_months_forecast": round(float(next_6["forecast_net_revenue"].sum()), 2),
        "next_12_months_forecast": round(forecast_12_total, 2),
        "next_12_months_low_95": round(float(next_12["lower_95"].sum()), 2),
        "next_12_months_high_95": round(float(next_12["upper_95"].sum()), 2),
        "trailing_12_actual": round(trailing_12, 2),
        "implied_growth_pct": round((forecast_12_total / trailing_12 - 1) * 100, 1),
        "first_month_forecast": round(float(best_rows.iloc[0]["forecast_net_revenue"]), 2),
        "first_month_label": best_rows.index[0],
    }
    forecast_df.to_csv(PROCESSED_DIR / "forecast_monthly.csv", index=False)
    with open(PROCESSED_DIR / "forecast_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)

    make_figures(series, forecast_df, backtest_df, best_model, snapshot)
    print(json.dumps({k: v for k, v in summary.items() if k != "backtest"}, indent=2))
    return summary


def make_figures(series, forecast_df, backtest_df, best_model, snapshot):
    sns.set_theme(style="whitegrid")

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(series.index, series.values, marker="o", label="Actual net revenue", color="#1f77b4")
    for name in MODEL_NAMES:
        part = forecast_df[forecast_df["model"] == name]
        idx = pd.to_datetime(part["forecast_month"])
        style = {"color": "#d62728", "lw": 2.2, "label": f"Forecast ({name})"} if name == best_model else {"color": "#999999", "lw": 1, "alpha": 0.7, "label": "_nolegend_"}
        ax.plot(idx, part["forecast_net_revenue"], linestyle="--", **style)
    best_part = forecast_df[forecast_df["model"] == best_model]
    idx = pd.to_datetime(best_part["forecast_month"])
    ax.fill_between(idx, best_part["lower_95"], best_part["upper_95"], color="#d62728", alpha=0.15, label="95% interval (best model)")
    ax.axvline(snapshot, color="k", linestyle=":", alpha=0.6)
    ax.set_title(f"Monthly Net Revenue: Actual vs 12-Month Forecast ({best_model})")
    ax.set_ylabel("Net revenue (£)")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "forecast_next_12months.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    ok = backtest_df[backtest_df["wmape_pct"].notna()]
    sns.barplot(data=ok, x="model", y="wmape_pct", ax=ax, color="#1f77b4")
    ax.set_title("Backtest Accuracy: WMAPE % on Last 6 Months (lower is better)")
    ax.set_xlabel("")
    ax.set_ylabel("WMAPE %")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.1f%%")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "forecast_backtest_wmape.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(series.index, series.values, marker="o", label="Actual", color="#1f77b4")
    for name in MODEL_NAMES:
        part = forecast_df[forecast_df["model"] == name]
        idx = pd.to_datetime(part["forecast_month"])
        ax.plot(idx, part["forecast_net_revenue"], linestyle="--", lw=1.4, label=name)
    ax.set_title("Model Comparison: 12-Month Forecasts")
    ax.set_ylabel("Net revenue (£)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "forecast_model_comparison.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    run()
