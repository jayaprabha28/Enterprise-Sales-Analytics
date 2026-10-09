DROP TABLE IF EXISTS fact_returns CASCADE;
DROP TABLE IF EXISTS fact_sales CASCADE;
DROP TABLE IF EXISTS dim_customer CASCADE;
DROP TABLE IF EXISTS dim_product CASCADE;
DROP TABLE IF EXISTS dim_country CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;
DROP VIEW IF EXISTS vw_monthly_revenue CASCADE;
DROP VIEW IF EXISTS vw_customer_orders CASCADE;

CREATE TABLE dim_date (
    date_key       INTEGER PRIMARY KEY,
    full_date      DATE NOT NULL UNIQUE,
    year           INTEGER NOT NULL,
    quarter        INTEGER NOT NULL,
    month          INTEGER NOT NULL,
    month_name     TEXT NOT NULL,
    year_month     TEXT NOT NULL,
    iso_week       INTEGER NOT NULL,
    year_week      TEXT NOT NULL,
    day_of_week    INTEGER NOT NULL,
    day_name       TEXT NOT NULL,
    is_weekend     BOOLEAN NOT NULL,
    is_month_start BOOLEAN NOT NULL,
    is_month_end   BOOLEAN NOT NULL,
    week_starting  DATE NOT NULL
);

CREATE TABLE dim_country (
    country_key SERIAL PRIMARY KEY,
    country     TEXT NOT NULL UNIQUE,
    region      TEXT NOT NULL,
    country_iso TEXT NOT NULL
);

CREATE TABLE dim_product (
    product_key      SERIAL PRIMARY KEY,
    stockcode        TEXT NOT NULL UNIQUE,
    description      TEXT NOT NULL,
    category         TEXT NOT NULL,
    is_service       BOOLEAN NOT NULL,
    typical_price    NUMERIC(12,3),
    launch_date      DATE,
    discontinued_date DATE
);

CREATE TABLE dim_customer (
    customer_key    SERIAL PRIMARY KEY,
    customer_id     BIGINT NOT NULL UNIQUE,
    country         TEXT NOT NULL,
    region          TEXT NOT NULL,
    country_key     INTEGER REFERENCES dim_country(country_key),
    first_order_date DATE NOT NULL,
    last_order_date  DATE NOT NULL,
    orders          INTEGER NOT NULL,
    gross_revenue   NUMERIC(14,2) NOT NULL,
    refund_amount   NUMERIC(14,2) NOT NULL,
    net_revenue     NUMERIC(14,2) NOT NULL,
    cohort_month    TEXT NOT NULL,
    tenure_days     INTEGER NOT NULL,
    country_iso     TEXT NOT NULL
);

CREATE TABLE fact_sales (
    line_id      BIGINT PRIMARY KEY,
    invoice      TEXT NOT NULL,
    date_key     INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key INTEGER REFERENCES dim_customer(customer_key),
    product_key  INTEGER NOT NULL REFERENCES dim_product(product_key),
    country_key  INTEGER NOT NULL REFERENCES dim_country(country_key),
    quantity     INTEGER NOT NULL,
    unit_price   NUMERIC(12,3) NOT NULL,
    line_revenue NUMERIC(14,2) NOT NULL,
    is_service   BOOLEAN NOT NULL
);

CREATE TABLE fact_returns (
    return_id    BIGINT PRIMARY KEY,
    invoice      TEXT NOT NULL,
    date_key     INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key INTEGER REFERENCES dim_customer(customer_key),
    product_key  INTEGER NOT NULL REFERENCES dim_product(product_key),
    country_key  INTEGER NOT NULL REFERENCES dim_country(country_key),
    quantity     INTEGER NOT NULL,
    unit_price   NUMERIC(12,3) NOT NULL,
    refund_amount NUMERIC(14,2) NOT NULL
);

CREATE INDEX ix_sales_date ON fact_sales(date_key);
CREATE INDEX ix_sales_customer ON fact_sales(customer_key);
CREATE INDEX ix_sales_product ON fact_sales(product_key);
CREATE INDEX ix_sales_country ON fact_sales(country_key);
CREATE INDEX ix_sales_invoice ON fact_sales(invoice);
CREATE INDEX ix_returns_date ON fact_returns(date_key);
CREATE INDEX ix_returns_customer ON fact_returns(customer_key);
CREATE INDEX ix_returns_product ON fact_returns(product_key);
CREATE INDEX ix_customer_cohort ON dim_customer(cohort_month);

CREATE VIEW vw_monthly_revenue AS
SELECT d.year_month,
       SUM(f.line_revenue) AS gross_revenue,
       COUNT(DISTINCT f.invoice) AS orders
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
GROUP BY d.year_month;

CREATE VIEW vw_customer_orders AS
SELECT f.customer_key,
       c.customer_id,
       d.full_date,
       f.invoice,
       f.line_revenue
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
LEFT JOIN dim_customer c ON f.customer_key = c.customer_key
WHERE f.customer_key IS NOT NULL;
