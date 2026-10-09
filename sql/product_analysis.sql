-- Category, product rank, like-for-like growth, return hotspot and price position queries.
-- @name: category_performance
WITH category_sales AS (
    SELECT p.category,
           SUM(f.line_revenue) AS gross_revenue,
           COUNT(DISTINCT f.invoice) AS orders,
           SUM(f.quantity) AS units,
           COUNT(DISTINCT f.customer_key) AS customers,
           AVG(f.unit_price) AS avg_unit_price
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    WHERE p.is_service = false
    GROUP BY p.category
),
category_returns AS (
    SELECT p.category,
           SUM(r.refund_amount) AS refund_amount
    FROM fact_returns r
    JOIN dim_product p ON r.product_key = p.product_key
    WHERE p.is_service = false
    GROUP BY p.category
)
SELECT s.category,
       ROUND(s.gross_revenue - COALESCE(rt.refund_amount, 0), 2) AS net_revenue,
       s.orders,
       s.units,
       s.customers,
       ROUND(COALESCE(rt.refund_amount, 0), 2) AS refund_amount,
       ROUND(100.0 * COALESCE(rt.refund_amount, 0) / NULLIF(s.gross_revenue, 0), 2) AS return_rate_pct,
       ROUND(s.avg_unit_price, 3) AS avg_unit_price,
       ROUND(100.0 * (s.gross_revenue - COALESCE(rt.refund_amount, 0))
             / SUM(s.gross_revenue - COALESCE(rt.refund_amount, 0)) OVER (), 2) AS share_of_revenue_pct
FROM category_sales s
LEFT JOIN category_returns rt ON rt.category = s.category
ORDER BY net_revenue DESC;

-- @name: top_bottom_products
WITH product_net AS (
    SELECT u.product_key,
           SUM(u.amount) AS net_revenue
    FROM (
        SELECT product_key, line_revenue AS amount
        FROM fact_sales
        UNION ALL
        SELECT product_key, -refund_amount
        FROM fact_returns
    ) u
    GROUP BY u.product_key
),
ranked AS (
    SELECT p.stockcode,
           p.description,
           p.category,
           ROUND(n.net_revenue, 2) AS net_revenue,
           ROW_NUMBER() OVER (ORDER BY n.net_revenue DESC) AS rn_desc,
           ROW_NUMBER() OVER (ORDER BY n.net_revenue ASC) AS rn_asc
    FROM product_net n
    JOIN dim_product p ON p.product_key = n.product_key
    WHERE p.is_service = false
)
SELECT label, rank, stockcode, description, category, net_revenue
FROM (
    SELECT 'Top' AS label,
           rn_desc AS rank,
           stockcode, description, category, net_revenue
    FROM ranked
    WHERE rn_desc <= 10
    UNION ALL
    SELECT 'Bottom' AS label,
           rn_asc AS rank,
           stockcode, description, category, net_revenue
    FROM ranked
    WHERE rn_asc <= 10
) t
ORDER BY label DESC, rank;

-- @name: product_growth_like_for_like
WITH window_revenue AS (
    SELECT p.product_key,
           p.stockcode,
           p.description,
           SUM(f.line_revenue) FILTER (
               WHERE d.full_date BETWEEN '2010-01-01' AND '2010-12-09') AS revenue_2010,
           SUM(f.line_revenue) FILTER (
               WHERE d.full_date BETWEEN '2011-01-01' AND '2011-12-09') AS revenue_2011
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    JOIN dim_product p ON f.product_key = p.product_key
    GROUP BY p.product_key, p.stockcode, p.description
    HAVING SUM(f.line_revenue) FILTER (
               WHERE d.full_date BETWEEN '2010-01-01' AND '2010-12-09') > 0
       AND SUM(f.line_revenue) FILTER (
               WHERE d.full_date BETWEEN '2011-01-01' AND '2011-12-09') > 0
),
growth AS (
    SELECT stockcode,
           description,
           revenue_2010,
           revenue_2011,
           ROUND(100.0 * (revenue_2011 - revenue_2010) / revenue_2010, 2) AS growth_pct
    FROM window_revenue
),
momentum AS (
    SELECT g.*,
           CASE
               WHEN g.growth_pct > 20 THEN 'Accelerating'
               WHEN g.growth_pct > 5 THEN 'Growing'
               WHEN g.growth_pct >= -5 THEN 'Flat'
               ELSE 'Declining'
           END AS momentum
    FROM growth g
)
SELECT stockcode,
       description,
       revenue_2010,
       revenue_2011,
       growth_pct,
       momentum
FROM momentum
WHERE momentum = 'Declining'
ORDER BY revenue_2011 DESC
LIMIT 20;

-- @name: product_return_hotspots
WITH product_sales AS (
    SELECT p.product_key,
           p.stockcode,
           p.description,
           p.category,
           SUM(f.line_revenue) AS revenue
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    GROUP BY p.product_key, p.stockcode, p.description, p.category
),
product_returns AS (
    SELECT r.product_key,
           SUM(r.refund_amount) AS refund_amount
    FROM fact_returns r
    GROUP BY r.product_key
),
combined AS (
    SELECT ps.stockcode,
           ps.description,
           ps.category,
           ps.revenue,
           COALESCE(pr.refund_amount, 0) AS refund_amount,
           100.0 * COALESCE(pr.refund_amount, 0) / NULLIF(ps.revenue, 0) AS refund_rate
    FROM product_sales ps
    LEFT JOIN product_returns pr ON pr.product_key = ps.product_key
),
hotspots AS (
    SELECT c.*,
           DENSE_RANK() OVER (ORDER BY c.refund_rate DESC) AS refund_rank
    FROM combined c
    WHERE c.refund_rate > 10
      AND c.revenue > 5000
)
SELECT stockcode,
       description,
       category,
       ROUND(revenue, 2) AS revenue,
       ROUND(refund_amount, 2) AS refund_amount,
       ROUND(refund_rate, 2) AS refund_rate,
       refund_rank
FROM hotspots
ORDER BY refund_rate DESC;

-- @name: price_position_analysis
WITH lines AS (
    SELECT p.category,
           f.line_revenue,
           CASE
               WHEN f.unit_price >= 1.05 * p.typical_price THEN 'Premium'
               WHEN f.unit_price <= 0.90 * p.typical_price THEN 'Discounted'
               ELSE 'Standard'
           END AS price_position,
           100.0 * (p.typical_price - f.unit_price) / p.typical_price AS discount_pct
    FROM fact_sales f
    JOIN dim_product p ON f.product_key = p.product_key
    WHERE p.typical_price > 0
)
SELECT category,
       price_position,
       COUNT(*) AS line_count,
       ROUND(SUM(line_revenue), 2) AS revenue,
       ROUND(AVG(discount_pct), 2) AS avg_discount_pct
FROM lines
GROUP BY category, price_position
ORDER BY category, price_position;
