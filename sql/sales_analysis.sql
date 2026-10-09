-- Revenue trend, growth, rolling, product rank, pareto, weekday and channel queries.
-- @name: monthly_revenue_trend
WITH monthly_sales AS (
    SELECT d.year_month,
           SUM(f.line_revenue) AS gross_revenue,
           COUNT(DISTINCT f.invoice) AS orders
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.year_month
),
monthly_refunds AS (
    SELECT d.year_month,
           SUM(r.refund_amount) AS refunds
    FROM fact_returns r
    JOIN dim_date d ON r.date_key = d.date_key
    GROUP BY d.year_month
)
SELECT s.year_month,
       s.gross_revenue,
       s.orders,
       COALESCE(rf.refunds, 0) AS refunds,
       s.gross_revenue - COALESCE(rf.refunds, 0) AS net_revenue,
       ROUND(100.0 * COALESCE(rf.refunds, 0) / NULLIF(s.gross_revenue, 0), 2) AS return_rate_pct
FROM monthly_sales s
LEFT JOIN monthly_refunds rf ON rf.year_month = s.year_month
ORDER BY s.year_month;

-- @name: mom_yoy_growth
WITH monthly_sales AS (
    SELECT d.year_month,
           SUM(f.line_revenue) AS gross_revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.year_month
),
monthly_refunds AS (
    SELECT d.year_month,
           SUM(r.refund_amount) AS refunds
    FROM fact_returns r
    JOIN dim_date d ON r.date_key = d.date_key
    GROUP BY d.year_month
),
monthly_net AS (
    SELECT s.year_month,
           s.gross_revenue - COALESCE(rf.refunds, 0) AS net_revenue
    FROM monthly_sales s
    LEFT JOIN monthly_refunds rf ON rf.year_month = s.year_month
)
SELECT year_month,
       net_revenue,
       LAG(net_revenue, 1) OVER (ORDER BY year_month) AS prev_month_revenue,
       ROUND(100.0 * (net_revenue - LAG(net_revenue, 1) OVER (ORDER BY year_month))
             / NULLIF(LAG(net_revenue, 1) OVER (ORDER BY year_month), 0), 2) AS mom_growth_pct,
       LAG(net_revenue, 12) OVER (ORDER BY year_month) AS prior_year_revenue,
       ROUND(100.0 * (net_revenue - LAG(net_revenue, 12) OVER (ORDER BY year_month))
             / NULLIF(LAG(net_revenue, 12) OVER (ORDER BY year_month), 0), 2) AS yoy_growth_pct
FROM monthly_net
ORDER BY year_month;

-- @name: rolling_averages_daily
WITH daily_revenue AS (
    SELECT d.full_date,
           SUM(f.line_revenue) AS daily_revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.full_date
)
SELECT full_date,
       daily_revenue,
       ROUND(AVG(daily_revenue) OVER (
           ORDER BY full_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS avg_7d_revenue,
       SUM(daily_revenue) OVER (
           ORDER BY full_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS rolling_30d_revenue
FROM daily_revenue
ORDER BY full_date;

-- @name: top_products_by_region
SELECT region,
       stockcode,
       description,
       revenue,
       rank
FROM (
    SELECT c.region,
           p.stockcode,
           p.description,
           SUM(u.amount) AS revenue,
           RANK() OVER (
               PARTITION BY c.region ORDER BY SUM(u.amount) DESC) AS rank
    FROM (
        SELECT product_key, country_key, line_revenue AS amount
        FROM fact_sales
        UNION ALL
        SELECT product_key, country_key, -refund_amount
        FROM fact_returns
    ) u
    JOIN dim_product p ON u.product_key = p.product_key
    JOIN dim_country c ON u.country_key = c.country_key
    GROUP BY c.region, p.stockcode, p.description
) ranked
WHERE rank <= 5
ORDER BY region, rank, revenue DESC;

-- @name: revenue_pareto
WITH product_revenue AS (
    SELECT p.stockcode,
           p.description,
           SUM(f.line_revenue) AS revenue
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    GROUP BY p.stockcode, p.description
),
totals AS (
    SELECT SUM(revenue) AS total_revenue
    FROM product_revenue
),
scored AS (
    SELECT pr.stockcode,
           pr.description,
           pr.revenue,
           pr.revenue / t.total_revenue AS share_ratio,
           SUM(pr.revenue) OVER (ORDER BY pr.revenue DESC) / t.total_revenue AS cumulative_ratio
    FROM product_revenue pr
    CROSS JOIN totals t
)
SELECT stockcode,
       description,
       ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * share_ratio, 4) AS share_pct,
       ROUND(100.0 * cumulative_ratio, 4) AS cumulative_share_pct,
       CASE
           WHEN cumulative_ratio <= 0.80 THEN 'A'
           WHEN cumulative_ratio <= 0.95 THEN 'B'
           ELSE 'C'
       END AS abc_class
FROM scored
ORDER BY revenue DESC;

-- @name: weekday_pattern
WITH day_stats AS (
    SELECT d.day_of_week,
           d.day_name,
           SUM(f.line_revenue) AS revenue,
           COUNT(DISTINCT f.invoice) AS orders
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.day_of_week, d.day_name
)
SELECT day_of_week,
       day_name,
       revenue,
       orders,
       ROUND(revenue / NULLIF(orders, 0), 2) AS avg_order_value,
       ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS revenue_share_pct
FROM day_stats
ORDER BY day_of_week;

-- @name: channel_guest_vs_registered
WITH monthly_split AS (
    SELECT d.year_month,
           SUM(f.line_revenue) FILTER (WHERE f.customer_key IS NULL) AS guest_revenue,
           SUM(f.line_revenue) FILTER (WHERE f.customer_key IS NOT NULL) AS registered_revenue,
           COUNT(DISTINCT f.invoice) FILTER (WHERE f.customer_key IS NULL) AS guest_orders,
           COUNT(DISTINCT f.invoice) FILTER (WHERE f.customer_key IS NOT NULL) AS registered_orders,
           SUM(f.line_revenue) AS total_revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.year_month
)
SELECT year_month,
       guest_revenue,
       registered_revenue,
       total_revenue,
       guest_orders,
       registered_orders,
       ROUND(100.0 * guest_revenue / NULLIF(total_revenue, 0), 2) AS guest_share_pct,
       ROUND(100.0 * registered_revenue / NULLIF(total_revenue, 0), 2) AS registered_share_pct
FROM monthly_split
ORDER BY year_month;
