"""RFM scoring, rule-based segments and K-Means customer segmentation."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from config import FIGURES_DIR, PROCESSED_DIR, RANDOM_STATE, SEGMENT_PROFILES


def load_customers():
    return pd.read_parquet(PROCESSED_DIR / "customer_features.parquet")


def score_rfm(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rec_rank = out["recency_days"].rank(method="first")
    freq_rank = out["frequency"].rank(method="first")
    mono_rank = out["monetary"].rank(method="first")
    out["r_score"] = pd.qcut(rec_rank, 5, labels=[5, 4, 3, 2, 1]).astype(int)
    out["f_score"] = pd.qcut(freq_rank, 5, labels=[1, 2, 3, 4, 5]).astype(int)
    out["m_score"] = pd.qcut(mono_rank, 5, labels=[1, 2, 3, 4, 5]).astype(int)
    out["rfm_score"] = out["r_score"] + out["f_score"] + out["m_score"]
    return out


def assign_rule_segments(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    conditions = [
        (out["tenure_days"] <= 90),
        (out["r_score"] >= 4) & (out["f_score"] >= 4) & (out["m_score"] >= 4),
        (out["f_score"] >= 4) & (out["r_score"] >= 3),
        (out["m_score"] >= 4) & (out["r_score"] >= 3),
        (out["r_score"] >= 4),
        (out["r_score"] <= 2) & (out["m_score"] >= 3),
        (out["recency_days"] > 180),
    ]
    choices = [
        "New Customers", "Champions", "Loyal Customers", "Big Spenders",
        "Potential Loyalists", "At Risk", "Lost",
    ]
    out["rfm_segment"] = np.select(conditions, choices, default="Hibernating")
    return out


def name_clusters(centroids: pd.DataFrame, df: pd.DataFrame) -> dict:
    median_freq = float(df["frequency"].median())
    median_mon = float(df["monetary"].median())
    names = {}
    for cluster, row in centroids.iterrows():
        rec, freq, mon = row["recency"], row["frequency"], row["monetary"]
        if rec <= 90 and freq >= median_freq and mon >= median_mon:
            label = "Champions"
        elif rec <= 120 and freq >= 4:
            label = "Loyal Customers"
        elif mon >= df["monetary"].quantile(0.75) and rec <= 150:
            label = "Big Spenders"
        elif rec <= 90:
            label = "Potential Loyalists"
        elif rec <= 180 and mon >= median_mon:
            label = "At Risk"
        elif rec > 180 and mon >= median_mon:
            label = "Hibernating"
        elif rec > 180:
            label = "Lost"
        else:
            label = "Hibernating"
        if label in names.values():
            label = f"{label} #{cluster}"
        names[cluster] = label
    return names


def run_kmeans(df: pd.DataFrame):
    def signed_log(values):
        return np.sign(values) * np.log1p(np.abs(values))

    features = np.column_stack([
        signed_log(df["recency_days"].to_numpy(dtype=float)),
        signed_log(df["frequency"].to_numpy(dtype=float)),
        signed_log(df["monetary"].to_numpy(dtype=float)),
    ])
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    rows = []
    models = {}
    for k in range(2, 9):
        model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels = model.fit_predict(scaled)
        score = silhouette_score(scaled, labels)
        rows.append({"k": k, "inertia": model.inertia_, "silhouette": round(score, 4)})
        models[k] = (model, labels)
    curve = pd.DataFrame(rows)
    best_k = int(curve.loc[curve["silhouette"].idxmax(), "k"])
    model, labels = models[best_k]
    silhouette = round(float(silhouette_score(scaled, labels)), 4)
    out = df.copy()
    out["cluster"] = labels
    centroids = out.groupby("cluster").agg(
        recency=("recency_days", "median"),
        frequency=("frequency", "median"),
        monetary=("monetary", "median"),
    )
    name_map = name_clusters(centroids, out)
    out["kmeans_segment"] = out["cluster"].map(name_map)
    return out, curve, best_k, silhouette, name_map


def summarise(df: pd.DataFrame, best_k: int, silhouette: float):
    segment_stats = df.groupby("rfm_segment").agg(
        customers=("customer_id", "count"),
        revenue=("monetary", "sum"),
        avg_recency=("recency_days", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_monetary=("monetary", "mean"),
        churn_rate=("churned", "mean"),
    ).reset_index()
    segment_stats["revenue_share_pct"] = (segment_stats["revenue"] / segment_stats["revenue"].sum() * 100).round(2)
    segment_stats = segment_stats.sort_values("revenue", ascending=False).reset_index(drop=True)
    summary = {
        "customers_segmented": int(len(df)),
        "best_k": best_k,
        "silhouette": silhouette,
        "segment_profiles": SEGMENT_PROFILES,
        "segments": segment_stats.to_dict(orient="records"),
        "at_risk_plus_lost_revenue": round(float(
            segment_stats.loc[segment_stats["rfm_segment"].isin(["At Risk", "Lost", "Hibernating"]), "revenue"].sum()
        ), 2),
        "champions_plus_loyal_revenue_share_pct": round(float(
            segment_stats.loc[segment_stats["rfm_segment"].isin(["Champions", "Loyal Customers"]), "revenue_share_pct"].sum()
        ), 2),
    }
    return summary, segment_stats


def make_figures(df: pd.DataFrame, segment_stats: pd.DataFrame, curve: pd.DataFrame):
    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(data=segment_stats.sort_values("revenue"), x="revenue", y="rfm_segment", ax=ax, color="#1f77b4")
    ax.set_title("Net Revenue by Customer Segment")
    ax.set_xlabel("Monetary (£)")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "segment_revenue_bar.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.scatterplot(
        data=df, x="recency_days", y="frequency", hue="rfm_segment",
        size="monetary", sizes=(20, 400), alpha=0.65, ax=ax, palette="tab10",
    )
    ax.set_title("Customer Segments: Recency vs Frequency (size = Monetary)")
    ax.set_xlabel("Recency (days since last order)")
    ax.set_ylabel("Frequency (orders)")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "rfm_scatter_segments.png", dpi=130)
    plt.close(fig)

    profile = df.groupby("rfm_segment")[["r_score", "f_score", "m_score"]].mean().round(2)
    profile = profile.loc[segment_stats["rfm_segment"]]
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.heatmap(profile, annot=True, cmap="YlGnBu", ax=ax, fmt=".2f")
    ax.set_title("Average RFM Scores by Segment")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "segment_rfm_heatmap.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(curve["k"], curve["silhouette"], marker="o")
    ax.set_title("K-Means Silhouette by k")
    ax.set_xlabel("k")
    ax.set_ylabel("Silhouette")
    ax.set_xticks(curve["k"])
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "kmeans_selection.png", dpi=130)
    plt.close(fig)


def run():
    df = load_customers()
    df = score_rfm(df)
    df = assign_rule_segments(df)
    df, curve, best_k, silhouette, name_map = run_kmeans(df)
    summary, segment_stats = summarise(df, best_k, silhouette)

    df.to_parquet(PROCESSED_DIR / "customer_segments.parquet", index=False)
    df.to_csv(PROCESSED_DIR / "customer_segments.csv", index=False)
    segment_stats.to_csv(PROCESSED_DIR / "segment_stats.csv", index=False)
    curve.to_csv(PROCESSED_DIR / "kmeans_curve.csv", index=False)
    with open(PROCESSED_DIR / "segmentation_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)

    make_figures(df, segment_stats, curve)
    print(json.dumps({k: v for k, v in summary.items() if k != "segments"}, indent=2))
    return summary


if __name__ == "__main__":
    run()
