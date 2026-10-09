-- Customer RFM, cohort, LTV, new-vs-returning and churn-signal queries.
-- @name: rfm_segmentation_sql
WITH customer_activity AS (
    SELECT f.customer_key,
           MAX(d.full_date) AS last_activity_date,
           COUNT(DISTINCT f.invoice) AS frequency,
           SUM(f.line_revenue) AS gross_revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE f.customer_key IS NOT NULL
    GROUP BY f.customer_key
),
customer_refunds AS (
    SELECT customer_key,
           SUM(refund_amount) AS refund_amount
    FROM fact_returns
    WHERE customer_key IS NOT NULL
    GROUP BY customer_key
),
base AS (
    SELECT ca.customer_key,
           (SELECT MAX(full_date) FROM dim_date) - ca.last_activity_date AS recency_days,
           ca.frequency,
           ca.gross_revenue - COALESCE(cr.refund_amount, 0) AS monetary
    FROM customer_activity ca
    LEFT JOIN customer_refunds cr ON cr.customer_key = ca.customer_key
),
scored AS (
    SELECT b.*,
           6 - NTILE(5) OVER (ORDER BY recency_days ASC) AS r_score,
           6 - NTILE(5) OVER (ORDER BY frequency DESC) AS f_score,
           6 - NTILE(5) OVER (ORDER BY monetary DESC) AS m_score
    FROM base b
)
SELECT c.customer_id,
       c.country,
       s.recency_days,
       s.frequency,
       ROUND(s.monetary, 2) AS monetary,
       s.r_score,
       s.f_score,
       s.m_score,
       CASE
           WHEN s.r_score >= 4 AND s.f_score >= 4 AND s.m_score >= 4 THEN 'Champions'
           WHEN s.r_score >= 3 AND s.f_score >= 4 THEN 'Loyal'
           WHEN s.r_score >= 4 AND s.f_score <= 2 THEN 'Potential Loyalist'
           WHEN s.r_score <= 2 AND s.m_score >= 3 THEN 'At Risk'
           WHEN s.r_score <= 2 AND s.f_score <= 2 THEN 'Hibernating'
           WHEN s.m_score >= 4 THEN 'Big Spenders'
           ELSE 'Other'
       END AS segment
FROM scored s
JOIN dim_customer c ON c.customer_key = s.customer_key
ORDER BY s.monetary DESC;

-- @name: cohort_retention
WITH activity AS (
    SELECT DISTINCT
           f.customer_key,
           d.year_month
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE f.customer_key IS NOT NULL
),
cohort_map AS (
    SELECT customer_key,
           MIN(year_month) AS cohort_month
    FROM activity
    GROUP BY customer_key
),
cohort_sizes AS (
    SELECT cohort_month,
           COUNT(*) AS cohort_size
    FROM cohort_map
    GROUP BY cohort_month
),
customer_months AS (
    SELECT cm.cohort_month,
           a.year_month AS activity_month,
           (SUBSTRING(a.year_month FROM 1 FOR 4)::INT * 12 + SUBSTRING(a.year_month FROM 6 FOR 2)::INT)
           - (SUBSTRING(cm.cohort_month FROM 1 FOR 4)::INT * 12 + SUBSTRING(cm.cohort_month FROM 6 FOR 2)::INT) AS month_index
    FROM activity a
    JOIN cohort_map cm ON cm.customer_key = a.customer_key
)
SELECT m.cohort_month,
       m.activity_month,
       m.month_index,
       COUNT(*) AS active_customers,
       cs.cohort_size,
       ROUND(100.0 * COUNT(*) / cs.cohort_size, 2) AS retention_pct
FROM customer_months m
JOIN cohort_sizes cs ON cs.cohort_month = m.cohort_month
WHERE m.month_index BETWEEN 0 AND 12
GROUP BY m.cohort_month, m.activity_month, m.month_index, cs.cohort_size
ORDER BY m.cohort_month, m.month_index;

-- @name: customer_lifetime_value
WITH customer_sales AS (
    SELECT f.customer_key,
           SUM(f.line_revenue) AS gross_revenue
    FROM fact_sales f
    WHERE f.customer_key IS NOT NULL
    GROUP BY f.customer_key
),
customer_refunds AS (
    SELECT customer_key,
           SUM(refund_amount) AS refund_amount
    FROM fact_returns
    WHERE customer_key IS NOT NULL
    GROUP BY customer_key
),
monetary AS (
    SELECT s.customer_key,
           s.gross_revenue - COALESCE(r.refund_amount, 0) AS revenue
    FROM customer_sales s
    LEFT JOIN customer_refunds r ON r.customer_key = s.customer_key
),
totals AS (
    SELECT SUM(revenue) AS total_revenue
    FROM monetary
),
running AS (
    SELECT m.customer_key,
           m.revenue,
           SUM(m.revenue) OVER (ORDER BY m.revenue DESC) AS running_total,
           ROW_NUMBER() OVER (ORDER BY m.revenue DESC) AS revenue_rank
    FROM monetary m
),
ranked AS (
    SELECT r.*,
           100.0 * r.revenue_rank / COUNT(*) OVER () AS rank_pct
    FROM running r
)
SELECT c.customer_id,
       c.country,
       ROUND(r.revenue, 2) AS revenue,
       ROUND(r.running_total, 2) AS running_total,
       ROUND(100.0 * r.running_total / t.total_revenue, 4) AS cum_share_pct,
       CASE
           WHEN r.rank_pct <= 1 THEN 'Top 1%'
           WHEN r.rank_pct <= 10 THEN 'Top 10%'
           WHEN r.rank_pct <= 20 THEN 'Top 20%'
           ELSE 'Rest'
       END AS tier
FROM ranked r
CROSS JOIN totals t
JOIN dim_customer c ON c.customer_key = r.customer_key
ORDER BY r.revenue DESC;

-- @name: new_vs_returning_monthly
WITH customer_invoices AS (
    SELECT DISTINCT
           f.customer_key,
           f.invoice,
           d.year_month
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE f.customer_key IS NOT NULL
),
invoice_classification AS (
    SELECT invoice,
           year_month,
           MIN(year_month) OVER (PARTITION BY customer_key) AS first_purchase_month
    FROM customer_invoices
),
invoice_revenue AS (
    SELECT invoice,
           SUM(line_revenue) AS invoice_revenue
    FROM fact_sales
    GROUP BY invoice
),
monthly AS (
    SELECT ic.year_month,
           SUM(ir.invoice_revenue) FILTER (WHERE ic.year_month = ic.first_purchase_month) AS new_revenue,
           SUM(ir.invoice_revenue) FILTER (WHERE ic.year_month <> ic.first_purchase_month) AS returning_revenue,
           COUNT(DISTINCT ic.invoice) FILTER (WHERE ic.year_month = ic.first_purchase_month) AS new_orders,
           COUNT(DISTINCT ic.invoice) FILTER (WHERE ic.year_month <> ic.first_purchase_month) AS returning_orders,
           SUM(ir.invoice_revenue) AS total_revenue
    FROM invoice_classification ic
    JOIN invoice_revenue ir ON ir.invoice = ic.invoice
    GROUP BY ic.year_month
)
SELECT year_month,
       new_revenue,
       returning_revenue,
       total_revenue,
       new_orders,
       returning_orders,
       ROUND(100.0 * new_revenue / NULLIF(total_revenue, 0), 2) AS new_share_pct,
       ROUND(100.0 * returning_revenue / NULLIF(total_revenue, 0), 2) AS returning_share_pct
FROM monthly
ORDER BY year_month;

-- @name: purchase_gap_churn_signals
WITH purchase_days AS (
    SELECT DISTINCT
           f.customer_key,
           d.full_date
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE f.customer_key IS NOT NULL
),
gaps AS (
    SELECT customer_key,
           full_date,
           full_date - LAG(full_date) OVER (
               PARTITION BY customer_key ORDER BY full_date) AS gap_days
    FROM purchase_days
),
customer_stats AS (
    SELECT customer_key,
           MAX(full_date) AS last_purchase_date,
           AVG(gap_days) AS avg_gap_days,
           (SELECT MAX(full_date) FROM dim_date) - MAX(full_date) AS recency_days
    FROM gaps
    GROUP BY customer_key
),
risk AS (
    SELECT s.customer_key,
           s.last_purchase_date,
           s.avg_gap_days,
           s.recency_days,
           CASE
               WHEN s.recency_days > 90 THEN 'Churned'
               WHEN s.avg_gap_days > 60 THEN 'At Risk'
               ELSE 'Active'
           END AS risk_level
    FROM customer_stats s
),
customer_revenue AS (
    SELECT customer_key,
           SUM(line_revenue) AS gross_revenue
    FROM fact_sales
    WHERE customer_key IS NOT NULL
    GROUP BY customer_key
),
customer_refunds AS (
    SELECT customer_key,
           SUM(refund_amount) AS refund_amount
    FROM fact_returns
    WHERE customer_key IS NOT NULL
    GROUP BY customer_key
),
risk_with_revenue AS (
    SELECT r.risk_level,
           COALESCE(cr.gross_revenue, 0) - COALESCE(rf.refund_amount, 0) AS net_revenue
    FROM risk r
    LEFT JOIN customer_revenue cr ON cr.customer_key = r.customer_key
    LEFT JOIN customer_refunds rf ON rf.customer_key = r.customer_key
)
SELECT risk_level,
       COUNT(*) AS customers,
       ROUND(SUM(net_revenue), 2) AS net_revenue,
       ROUND(100.0 * SUM(net_revenue) / SUM(SUM(net_revenue)) OVER (), 2) AS revenue_share_pct,
       ROUND(AVG(net_revenue), 2) AS avg_net_revenue
FROM risk_with_revenue
GROUP BY risk_level
ORDER BY customers DESC;
