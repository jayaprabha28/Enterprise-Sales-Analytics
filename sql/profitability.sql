-- Revenue waterfall, region ranking, decile concentration and price realization queries.
-- @name: revenue_waterfall
WITH yearly AS (
    SELECT d.year,
           SUM(f.line_revenue) AS gross_revenue,
           0::NUMERIC AS refunds
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.year
    UNION ALL
    SELECT d.year,
           0::NUMERIC,
           SUM(r.refund_amount)
    FROM fact_returns r
    JOIN dim_date d ON r.date_key = d.date_key
    GROUP BY d.year
),
yearly_agg AS (
    SELECT year,
           SUM(gross_revenue) AS gross_revenue,
           SUM(refunds) AS refunds
    FROM yearly
    GROUP BY year
)
SELECT period,
       ROUND(gross_revenue, 2) AS gross_revenue,
       ROUND(refunds, 2) AS refunds,
       ROUND(gross_revenue - refunds, 2) AS net_revenue,
       ROUND(100.0 * refunds / NULLIF(gross_revenue, 0), 2) AS return_cost_pct
FROM (
    SELECT year::TEXT AS period,
           gross_revenue,
           refunds
    FROM yearly_agg
    UNION ALL
    SELECT 'Total',
           SUM(gross_revenue),
           SUM(refunds)
    FROM yearly_agg
) t
ORDER BY period;

-- @name: net_revenue_by_region_country
WITH country_sales AS (
    SELECT c.region,
           c.country,
           SUM(f.line_revenue) AS gross_revenue,
           COUNT(DISTINCT f.invoice) AS orders,
           COUNT(DISTINCT f.customer_key) AS customers
    FROM fact_sales f
    JOIN dim_country c ON f.country_key = c.country_key
    GROUP BY c.region, c.country
),
country_returns AS (
    SELECT c.region,
           c.country,
           SUM(r.refund_amount) AS refunds
    FROM fact_returns r
    JOIN dim_country c ON r.country_key = c.country_key
    GROUP BY c.region, c.country
)
SELECT s.region,
       s.country,
       ROUND(s.gross_revenue, 2) AS gross_revenue,
       ROUND(COALESCE(rf.refunds, 0), 2) AS refunds,
       ROUND(s.gross_revenue - COALESCE(rf.refunds, 0), 2) AS net_revenue,
       ROUND(100.0 * COALESCE(rf.refunds, 0) / NULLIF(s.gross_revenue, 0), 2) AS return_rate_pct,
       s.orders,
       s.customers,
       ROUND((s.gross_revenue - COALESCE(rf.refunds, 0)) / NULLIF(s.customers, 0), 2) AS revenue_per_customer,
       RANK() OVER (
           PARTITION BY s.region
           ORDER BY s.gross_revenue - COALESCE(rf.refunds, 0) DESC) AS rank_in_region
FROM country_sales s
LEFT JOIN country_returns rf ON rf.region = s.region AND rf.country = s.country
ORDER BY s.region, rank_in_region;

-- @name: customer_contribution_concentration
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
customer_net AS (
    SELECT s.customer_key,
           s.gross_revenue - COALESCE(r.refund_amount, 0) AS net_revenue
    FROM customer_sales s
    LEFT JOIN customer_refunds r ON r.customer_key = s.customer_key
),
deciled AS (
    SELECT customer_key,
           net_revenue,
           NTILE(10) OVER (ORDER BY net_revenue) AS decile
    FROM customer_net
)
SELECT decile,
       COUNT(*) AS customers,
       ROUND(SUM(net_revenue), 2) AS revenue,
       ROUND(AVG(net_revenue), 2) AS avg_revenue,
       ROUND(100.0 * SUM(net_revenue) / SUM(SUM(net_revenue)) OVER (), 2) AS share_pct
FROM deciled
GROUP BY decile
ORDER BY decile;

-- @name: price_realization
WITH lines AS (
    SELECT p.category,
           f.line_revenue,
           CASE
               WHEN f.unit_price >= 1.05 * p.typical_price THEN 'Premium'
               WHEN f.unit_price <= 0.90 * p.typical_price THEN 'Discounted'
               ELSE 'Standard'
           END AS price_position
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    WHERE p.typical_price > 0
)
SELECT category,
       ROUND(SUM(line_revenue) FILTER (WHERE price_position = 'Premium'), 2) AS premium_revenue,
       ROUND(SUM(line_revenue) FILTER (WHERE price_position = 'Standard'), 2) AS standard_revenue,
       ROUND(SUM(line_revenue) FILTER (WHERE price_position = 'Discounted'), 2) AS discounted_revenue,
       ROUND(SUM(line_revenue), 2) AS total_revenue,
       ROUND(100.0 * SUM(line_revenue) FILTER (WHERE price_position = 'Discounted')
             / NULLIF(SUM(line_revenue), 0), 2) AS revenue_at_risk_pct
FROM lines
GROUP BY category
ORDER BY total_revenue DESC;

-- @name: high_revenue_low_retention_watchlist
WITH category_sales AS (
    SELECT p.category,
           SUM(f.line_revenue) AS gross_revenue
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    GROUP BY p.category
),
category_returns AS (
    SELECT p.category,
           SUM(r.refund_amount) AS refund_amount
    FROM fact_returns r
    JOIN dim_product p ON r.product_key = p.product_key
    GROUP BY p.category
),
category_agg AS (
    SELECT s.category,
           s.gross_revenue,
           COALESCE(rf.refund_amount, 0) AS refund_amount,
           100.0 * COALESCE(rf.refund_amount, 0) / NULLIF(s.gross_revenue, 0) AS refund_rate
    FROM category_sales s
    LEFT JOIN category_returns rf ON rf.category = s.category
),
medians AS (
    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gross_revenue) AS median_revenue,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY refund_rate) AS median_refund_rate
    FROM category_agg
)
SELECT c.category,
       ROUND(c.gross_revenue, 2) AS gross_revenue,
       ROUND(c.refund_amount, 2) AS refund_amount,
       ROUND(c.refund_rate, 2) AS refund_rate,
       ROUND(m.median_revenue::NUMERIC, 2) AS median_revenue,
       ROUND(m.median_refund_rate::NUMERIC, 2) AS median_refund_rate,
       CASE
           WHEN c.gross_revenue >= m.median_revenue AND c.refund_rate <= m.median_refund_rate THEN 'Star'
           WHEN c.gross_revenue >= m.median_revenue AND c.refund_rate > m.median_refund_rate THEN 'Bleed'
           WHEN c.gross_revenue < m.median_revenue AND c.refund_rate <= m.median_refund_rate THEN 'Niche'
           ELSE 'Low'
       END AS quadrant
FROM category_agg c
CROSS JOIN medians m
ORDER BY c.gross_revenue DESC;
