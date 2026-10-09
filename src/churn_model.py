"""Customer churn prediction: Logistic Regression, Random Forest and XGBoost with a leakage-free temporal design."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from config import FIGURES_DIR, PROCESSED_DIR, RANDOM_STATE, RISK_THRESHOLDS

NUMERIC_FEATURES = [
    "recency_days", "frequency", "monetary", "total_units", "distinct_products",
    "purchase_days", "avg_discount_pct", "tenure_days", "avg_price_paid",
    "avg_units_per_order", "avg_purchase_gap_days", "orders_per_month",
    "weekend_order_share", "return_rate",
]


def load_inputs():
    sales = pd.read_parquet(PROCESSED_DIR / "fact_sales.parquet")
    returns = pd.read_parquet(PROCESSED_DIR / "fact_returns.parquet")
    sales["invoice_date"] = pd.to_datetime(sales["invoice_date"])
    returns["invoice_date"] = pd.to_datetime(returns["invoice_date"])
    return sales, returns


def build_training_set(sales, returns, dim_customer, dim_product):
    from feature_engineering import build_customer_features

    snapshot = sales["invoice_date"].max().normalize()
    cutoff = snapshot - pd.Timedelta(days=90)
    train_sales = sales[sales["invoice_date"] <= cutoff]
    train_returns = returns[returns["invoice_date"] <= cutoff]

    features = build_customer_features(train_sales, train_returns, dim_customer, dim_product, cutoff)
    active_after = set(sales.loc[sales["invoice_date"] > cutoff, "customer_id"].dropna().unique())
    features = features[features["recency_days"] <= 180].copy()
    features["churned_future"] = (~features["customer_id"].isin(active_after)).astype(int)
    return features, cutoff, snapshot


def build_model_frame(df: pd.DataFrame):
    X = df[NUMERIC_FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0)
    region_dummies = pd.get_dummies(df["region"].fillna("Unknown"), prefix="region", dtype=int)
    X = pd.concat([X, region_dummies], axis=1)
    return X


def model_zoo():
    return {
        "Logistic Regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE),
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
            n_jobs=-1, random_state=RANDOM_STATE,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=400, max_depth=6, learning_rate=0.1, subsample=0.9,
            colsample_bytree=0.9, eval_metric="logloss", random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
    }


def evaluate(features: pd.DataFrame):
    X = build_model_frame(features)
    y = features["churned_future"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE
    )
    metrics = []
    fitted = {}
    probabilities = {}
    for name, model in model_zoo().items():
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        metrics.append({
            "model": name,
            "auc": round(float(roc_auc_score(y_test, proba)), 4),
            "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, pred, zero_division=0)), 4),
            "train_rows": len(X_train),
            "test_rows": len(X_test),
            "churn_rate_pct": round(float(y.mean() * 100), 1),
        })
        fitted[name] = model
        probabilities[name] = (y_test, proba)
    metrics_df = pd.DataFrame(metrics)
    best_name = metrics_df.loc[metrics_df["auc"].idxmax(), "model"]
    return fitted, probabilities, metrics_df, best_name, X_train, X_test, y_test


def feature_importance_figure(fitted, best_name, X_train):
    model = fitted[best_name]
    if hasattr(model, "feature_importances_"):
        importances = pd.Series(model.feature_importances_, index=X_train.columns)
        title = f"Feature Importance ({best_name})"
    else:
        coef = model.named_steps["logisticregression"].coef_[0]
        importances = pd.Series(np.abs(coef), index=X_train.columns)
        title = f"|Coefficient| Magnitude ({best_name})"
    top = importances.sort_values(ascending=True).tail(15)
    fig, ax = plt.subplots(figsize=(9, 6))
    top.plot(kind="barh", ax=ax, color="#1f77b4")
    ax.set_title(title)
    ax.set_xlabel("Importance")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "churn_feature_importance.png", dpi=130)
    plt.close(fig)
    return top.sort_values(ascending=False)


def risk_levels(probabilities: pd.Series) -> pd.Series:
    high, medium = RISK_THRESHOLDS["high"], RISK_THRESHOLDS["medium"]
    return pd.Series(
        np.select([probabilities >= high, probabilities >= medium], ["High", "Medium"], default="Low"),
        index=probabilities.index,
        name="risk_level",
    )


def roc_figure(probabilities, metrics_df):
    fig, ax = plt.subplots(figsize=(9, 6))
    for name, (y_test, proba) in probabilities.items():
        fpr, tpr, _ = roc_curve(y_test, proba)
        auc = metrics_df.loc[metrics_df["model"] == name, "auc"].iloc[0]
        ax.plot(fpr, tpr, label=f"{name} (AUC={auc:.3f})")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5)
    ax.set_title("Churn Model ROC Curves (90-day forward window)")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "churn_roc_curves.png", dpi=130)
    plt.close(fig)


def run():
    sales, returns = load_inputs()
    dim_customer = pd.read_parquet(PROCESSED_DIR / "dim_customer.parquet")
    dim_product = pd.read_parquet(PROCESSED_DIR / "dim_product.parquet")
    training_features, cutoff, snapshot = build_training_set(sales, returns, dim_customer, dim_product)

    fitted, probabilities, metrics_df, best_name, X_train, X_test, y_test = evaluate(training_features)
    sns.set_theme(style="whitegrid")

    best_model = CalibratedClassifierCV(
        estimator=clone(fitted[best_name]), method="isotonic", cv=5
    ).fit(X_train, training_features.loc[X_train.index, "churned_future"])
    calibrated_proba = best_model.predict_proba(X_test)[:, 1]
    calibrated_pred = (calibrated_proba >= 0.5).astype(int)
    calibrated_metrics = {
        "model": f"{best_name} (calibrated)",
        "auc": round(float(roc_auc_score(y_test, calibrated_proba)), 4),
        "accuracy": round(float(accuracy_score(y_test, calibrated_pred)), 4),
        "precision": round(float(precision_score(y_test, calibrated_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, calibrated_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, calibrated_pred, zero_division=0)), 4),
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "churn_rate_pct": round(float(training_features["churned_future"].mean() * 100), 1),
    }
    probabilities[best_name] = (y_test, calibrated_proba)
    metrics_df = pd.concat([metrics_df, pd.DataFrame([calibrated_metrics])], ignore_index=True)

    scoring = pd.read_parquet(PROCESSED_DIR / "customer_segments.parquet")
    X_score = build_model_frame(scoring)
    X_score = X_score.reindex(columns=X_train.columns, fill_value=0)
    scoring["churn_probability"] = best_model.predict_proba(X_score)[:, 1].round(4)
    scoring["risk_level"] = risk_levels(scoring["churn_probability"])
    scoring["model_used"] = best_name

    roc_figure(probabilities, metrics_df)
    conf = confusion_matrix(y_test, (probabilities[best_name][1] >= 0.5).astype(int))
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(conf, annot=True, fmt="d", cmap="Blues", ax=ax,
                xticklabels=["Active", "Churned"], yticklabels=["Active", "Churned"])
    ax.set_title(f"Confusion Matrix ({best_name})")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "churn_confusion_matrix.png", dpi=130)
    plt.close(fig)

    importance = feature_importance_figure(fitted, best_name, X_train)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sns.histplot(scoring["churn_probability"], bins=40, ax=axes[0], color="#d62728")
    axes[0].set_title("Predicted Churn Probability Distribution")
    risk_counts = scoring["risk_level"].value_counts().reindex(["High", "Medium", "Low"]).fillna(0)
    sns.barplot(x=risk_counts.index, y=risk_counts.values, hue=risk_counts.index,
                palette=["#d62728", "#ff7f0e", "#2ca02c"], legend=False, ax=axes[1])
    axes[1].set_title("Customers by Risk Level")
    axes[1].set_ylabel("Customers")
    for container in axes[1].containers:
        axes[1].bar_label(container, fmt="%d")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "churn_risk_distribution.png", dpi=130)
    plt.close(fig)

    scoring_out = scoring[[
        "customer_id", "recency_days", "frequency", "monetary", "rfm_segment", "kmeans_segment",
        "churn_probability", "risk_level", "churned", "country", "region",
    ]].rename(columns={"churned": "churned_actual"})
    scoring_out.to_csv(PROCESSED_DIR / "churn_predictions.csv", index=False)
    metrics_df.to_csv(PROCESSED_DIR / "model_metrics.csv", index=False)

    revenue_by_risk = scoring.groupby("risk_level")["monetary"].sum().round(2).to_dict()
    summary = {
        "design": "Features up to cutoff, label = activity in following 90 days (no leakage)",
        "cutoff_date": str(cutoff.date()),
        "snapshot_date": str(snapshot.date()),
        "training_customers_active_at_cutoff": int(len(training_features)),
        "training_churn_rate_pct": round(float(training_features["churned_future"].mean() * 100), 1),
        "best_model": f"{best_name} + isotonic calibration",
        "best_raw_model": best_name,
        "metrics": metrics_df.to_dict(orient="records"),
        "scored_customers": int(len(scoring)),
        "risk_counts": scoring["risk_level"].value_counts().to_dict(),
        "revenue_by_risk": revenue_by_risk,
        "revenue_at_risk_high_pct": round(
            float(scoring.loc[scoring["risk_level"] == "High", "monetary"].sum() / scoring["monetary"].sum() * 100), 1
        ),
        "top_features": importance.head(8).round(4).to_dict(),
    }
    with open(PROCESSED_DIR / "churn_model_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("metrics", "top_features")}, indent=2))
    return summary


if __name__ == "__main__":
    run()
