"""Synthetic 5-crore (≈50M record) dataset generator — 10 tables, injected quality issues.

Add-on deliverable (the real-data pipeline is untouched). Deterministic (seeded RNG,
RANDOM_STATE=42). Outputs one parquet per table into `data/raw_synthetic/` plus a
`synthetic_data_quality_report.json` describing every injected defect and its
observed-vs-injected reconciliation.

Chunked generation keeps peak memory bounded while delivering ~50,000,000 rows:

    sales_transactions      40.0M   line-level raw fact (mirrors the real raw layout)
    inventory_snapshot      3.43M    weekly stock closes for SKUs
    returns                 2.4M    formal returns ledger
    campaign_responses      1.6M
    customer_support_tickets 1.2M
    customers               1.2M
    products               70.0k
    price_changes         620.0k
    salespeople              8.0k
    marketing_campaigns      2.0k
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config import COUNTRY_REGION_MAP, RANDOM_STATE, SERVICE_CODES, SYNTHETIC_DIR

SNAPSHOT = pd.Timestamp("2011-12-31")
START = pd.Timestamp("2010-01-01")
TOTAL_DAYS = (SNAPSHOT - START).days + 1  # 731
SEASONAL_FACTOR = np.array([1.0, 1.1, 1.0, 1.05, 1.05, 1.1, 1.15, 1.2, 1.15, 1.4, 1.65, 1.35], dtype=float)
WEEKDAY_BOOST = np.array([0.55, 1.1, 1.15, 1.15, 1.1, 1.05, 0.6], dtype=float)

SALES_LINES = 40_000_000
CHUNK = 2_000_000

SCALE = {
    "customers": 1_200_000,
    "products": 70_000,
    "salespeople": 8_000,
    "marketing_campaigns": 2_000,
    "returns": 2_400_000,
    "campaign_responses": 1_600_000,
    "customer_support_tickets": 1_200_000,
    "price_changes": 620_000,
    "inventory_snapshot": 66_000 * 52,  # 3,432,000
    "sales_transactions": SALES_LINES,
}
TOTAL_ROWS = sum(SCALE.values())  # ≈ 50.7M (~5 crore)

COUNTRIES = sorted(set(COUNTRY_REGION_MAP))
COUNTRY_WEIGHT = {
    "United Kingdom": 0.64, "Germany": 0.06, "EIRE": 0.05, "France": 0.05, "Netherlands": 0.03,
    "USA": 0.03, "Australia": 0.02, "Spain": 0.02, "Switzerland": 0.015, "Belgium": 0.015,
    "Italy": 0.015, "Sweden": 0.01, "Norway": 0.01, "Finland": 0.01, "Denmark": 0.01,
    "Portugal": 0.01, "Canada": 0.01, "Japan": 0.01, "Channel Islands": 0.004, "Unspecified": 0.001,
}
COUNTRY_P = np.array([COUNTRY_WEIGHT.get(c, 0.004) for c in COUNTRIES], dtype=float)
COUNTRY_P = COUNTRY_P / COUNTRY_P.sum()

NAME_PREFIX = ["Acme", "Global", "North", "Bright", "Blue", "Sterling", "Castle", "Harbor", "Pine",
               "Summit", "Crown", "Everest", "Meridian", "Oak", "Silver"]
NAME_SUFFIX = ["Trading", "Supplies", "Retail", "Imports", "Wholesale", "Distribution", "Housewares",
               "Store", "Outlet", "Co", "Furnishings", "Garden", "Lifestyle"]
FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
               "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Garcia", "Wilson",
              "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin"]

CATEGORY_SUBCATS = {
    "Christmas & Seasonal": ["Advent", "Tree", "Deco", "Stocking", "Garland"],
    "Lighting": ["Table", "Wall", "String", "Lamp", "Candle"],
    "Bags & Travel": ["Tote", "Shopper", "Luggage", "Make-up", "Backpack"],
    "Drinkware": ["Mug", "Glass", "Teapot", "Flask", "Cup"],
    "Kitchen & Dining": ["Plate", "Bowl", "Tray", "Jug", "Cake Stand"],
    "Home Décor": ["Frame", "Mirror", "Vase", "Ornament", "Wall Art"],
    "Stationery & Gifting": ["Card", "Notebook", "Wrap", "Pen", "Sticker"],
    "Bath & Storage": ["Basket", "Towel", "Soap", "Box", "Hanger"],
    "Toys & Games": ["Toy", "Puzzle", "Doll", "Blocks", "Game"],
    "Garden & Outdoor": ["Birdhouse", "Plant Stand", "Lantern", "Planter", "Wind Spinner"],
    "Textiles & Soft Furnishings": ["Cushion", "Throw", "Blanket", "Curtain", "Rug"],
    "Jewellery & Accessories": ["Necklace", "Bracelet", "Earring", "Scarf", "Ring"],
    "Other Products": ["Novelty", "Multi", "Set", "Bundle", "Misc"],
}
DESIGNWORDS = ["PREMIUM", "CLASSIC", "ROYAL", "MINI", "LARGE", "COLOURED", "ANTIQUE", "PACK", "WOODEN",
               "GLASS", "SET OF 6", "SET OF 12", "BRASS", "WHITE", "RED", "BLUE", "GOLD", "NATURAL"]

SVC = ["POST", "DOT", "M", "BANK CHARGES", "D", "S", "GIFT"]
SERVICE_DESCS = ["Postage & Delivery", "Postage & Delivery", "Manual Adjustments", "Bank Charges",
                 "Discounts & Giveaways", "Samples & Giveaways", "Gift Vouchers"]

REFUND_REASONS = ["Damaged in transit", "Wrong item", "Change of mind", "Not as described",
                  "Duplicate order", "Late delivery", "Quality issue"]
DISPOSITIONS = ["Refunded", "Refunded + restock", "Replacement sent"]

CAMPAIGN_CHANNELS = ["Email", "Postal", "Catalog", "Web", "Phone", "Partner"]
CAMPAIGN_TYPES = ["Acquisition", "Retention", "Seasonal", "Brand", "Co-op", "Win-back"]
TICKET_CATEGORIES = ["Billing", "Delivery", "Product", "Returns", "Technical", "Account"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
CHANNELS = ["Online", "Wholesale", "Retail", "Trade"]

INJECT_DEFECTS = {
    "sales": {
        "duplicate_rows_pct": 0.3, "null_customer_pct": 10.0, "negative_qty_pct": 2.0,
        "zero_qty_pct": 0.1, "negative_price_pct": 0.03, "zero_price_pct": 0.12,
        "future_date_pct": 0.1, "invalid_date_pct": 0.02, "lowercase_stockcode_pct": 0.5,
        "null_description_pct": 2.0, "outlier_qty_count": 8,
    },
    "customers": {"null_country_pct": 1.0},
    "products": {"null_description_pct": 2.0},
    "price_changes": {"null_reason_pct": 5.0},
    "tickets": {"negative_priority_count": 350, "satisfaction_9_count": 900},
    "inventory": {"negative_stock_pct": 0.08},
}

SALES_RAW_COLS = [
    "invoice", "stockcode", "description", "quantity", "invoice_date", "unit_price",
    "customer_id", "country", "channel", "promo_id", "salesperson_id",
]


def _rng():
    return np.random.default_rng(RANDOM_STATE)


def _invoice_array(seq) -> np.ndarray:
    return np.char.zfill((np.asarray(seq, dtype=np.int64) + 400_000).astype(str), 8)


def _day_weights() -> np.ndarray:
    days = pd.date_range(START, SNAPSHOT)
    w = SEASONAL_FACTOR[days.month.to_numpy() - 1] * WEEKDAY_BOOST[days.weekday.to_numpy()]
    return w / w.sum()


DAY_WEIGHTS = _day_weights()


def generate_customers(rng) -> pd.DataFrame:
    n = SCALE["customers"]
    is_b2b = rng.random(n) < 0.55
    name = np.where(
        is_b2b,
        rng.choice(NAME_PREFIX, n) + " " + rng.choice(NAME_SUFFIX, n),
        rng.choice(FIRST_NAMES, n) + " " + rng.choice(LAST_NAMES, n),
    )
    country = rng.choice(COUNTRIES, size=n, p=COUNTRY_P).astype(object)
    null_country = rng.random(n) < INJECT_DEFECTS["customers"]["null_country_pct"] / 100
    country[null_country] = np.nan
    region = np.array([COUNTRY_REGION_MAP.get(c, "Unknown") if isinstance(c, str) else "Unknown"
                       for c in country], dtype="object")
    df = pd.DataFrame({
        "customer_id": np.arange(10_000_001, 10_000_001 + n, dtype=np.int64),
        "customer_name": pd.Series(name.astype(str), dtype="string"),
        "country": pd.Series(country, dtype="object"),
        "region": pd.Series(region, dtype="string"),
        "signup_date": START + pd.to_timedelta(rng.integers(0, TOTAL_DAYS, size=n), unit="D"),
        "segment": rng.choice(["Retail", "Wholesale", "Corporate", "Consumer"], size=n,
                              p=[0.62, 0.22, 0.08, 0.08]),
        "tier": rng.choice(["Standard", "Silver", "Gold", "Platinum"], size=n, p=[0.7, 0.2, 0.08, 0.02]),
        "is_b2b": is_b2b,
        "is_active": rng.random(n) < 0.82,
    })
    return df


def generate_products(rng) -> pd.DataFrame:
    counts = rng.multinomial(SCALE["products"], [0.10, 0.10, 0.06, 0.10, 0.10, 0.09, 0.12, 0.06,
                                                 0.06, 0.04, 0.04, 0.04, 0.09])
    frames = []
    code = 1
    for cat, count in zip(CATEGORY_SUBCATS, counts):
        if count == 0:
            continue
        subcat = rng.choice(CATEGORY_SUBCATS[cat], count)
        design = rng.choice(DESIGNWORDS, count)
        base = np.round(rng.lognormal(2.4, 0.7, count), 2)
        desc = pd.Series((subcat + " " + design).astype(str), dtype="string").str.upper()
        frames.append(pd.DataFrame({
            "product_code": np.array([f"{code + i:04d}{chr(65 + (code + i) % 26)}" for i in range(count)]),
            "description": desc,
            "category": cat,
            "subcategory": subcat.astype(str),
            "base_price": base,
            "unit_cost": np.round(base * rng.uniform(0.45, 0.72, count), 2),
            "launch_date": START + pd.to_timedelta(rng.integers(0, max(TOTAL_DAYS - 400, 1), count), unit="D"),
            "is_active": rng.random(count) < 0.66,
        }))
        code += count
    products = pd.concat(frames, ignore_index=True)
    disc = rng.random(len(products)) < 0.34
    products["discontinued_date"] = products["launch_date"] + pd.to_timedelta(
        rng.integers(30, 400, len(products)), unit="D")
    products.loc[~disc, "discontinued_date"] = pd.NaT
    nnull = rng.random(len(products)) < INJECT_DEFECTS["products"]["null_description_pct"] / 100
    products.loc[nnull, "description"] = pd.NA

    svc = pd.DataFrame({
        "product_code": SVC,
        "description": pd.Series(SERVICE_DESCS, dtype="string"),
        "category": "Service",
        "subcategory": "Service",
        "base_price": 0.0,
        "unit_cost": 0.0,
        "launch_date": START,
        "discontinued_date": pd.NaT,
        "is_active": True,
    })
    return pd.concat([products, svc], ignore_index=True)


def _random_dup_seed(chunk_index: int, salt: str) -> int:
    return int(hashlib_hex(chunk_index, salt), 16) % (2 ** 32)


def hashlib_hex(a, b):
    import hashlib
    return hashlib.sha256(f"{a}:{b}".encode()).hexdigest()


def _sales_chunk(rng, products, customers, chunk_index, n_rows):
    d = INJECT_DEFECTS["sales"]
    n = int(n_rows)
    p_codes = products["product_code"].to_numpy()
    base_price = products["base_price"].to_numpy()
    description = products["description"].to_numpy(object)
    service_set = set(list(SERVICE_CODES) + ["GIFT", "BANK CHARGES"])
    is_service_row = np.array([c in service_set for c in p_codes])

    pop_w = (1.0 / (np.arange(len(p_codes)) + 1)) ** 0.6
    pop_w = pop_w / pop_w.sum()
    pi = rng.choice(len(p_codes), size=n, p=pop_w)

    pick_cust = rng.random(n) >= (d["null_customer_pct"] / 100)
    cust_ids = customers["customer_id"].to_numpy()
    cid = np.full(n, np.nan)
    cid[pick_cust] = rng.choice(cust_ids, size=int(pick_cust.sum())).astype(np.float64)
    cust_country_map = dict(zip(customers["customer_id"].to_numpy().tolist(),
                                customers["country"].to_numpy().tolist()))
    country = rng.choice(COUNTRIES, size=n, p=COUNTRY_P).astype(object)
    chosen = np.round(cid[pick_cust]).astype(np.int64)
    fill_values = np.array([cust_country_map.get(int(x)) for x in chosen], dtype=object)
    still_null = fill_values == None  # noqa: E711
    fill_values[still_null] = rng.choice(COUNTRIES, size=int(still_null.sum()), p=COUNTRY_P)
    country[pick_cust] = fill_values

    qty = np.clip(np.round(rng.lognormal(1.55, 1.05, n)), 1, 5000).astype(np.int64)
    price = np.round(base_price[pi] * (1 - (rng.random(n) < 0.18) * rng.uniform(0.05, 0.30, n)), 2)

    def _mutate_pct(double_, pct):
        cnt = int(n * pct / 100)
        return rng.choice(n, cnt, replace=False) if cnt else np.array([], dtype=np.int64)

    neg_price_idx = _mutate_pct(price, d["negative_price_pct"])
    price[neg_price_idx] = -np.round(rng.lognormal(2.0, 0.6, len(neg_price_idx)), 2)
    zero_price_idx = _mutate_pct(price, d["zero_price_pct"])
    price[zero_price_idx] = 0.0
    zero_qty_idx = _mutate_pct(qty, d["zero_qty_pct"])
    qty[zero_qty_idx] = 0
    neg_qty_idx = _mutate_pct(qty, d["negative_qty_pct"])
    qty[neg_qty_idx] = -np.clip(np.round(rng.lognormal(1.3, 0.9, len(neg_qty_idx))), 1, 300).astype(np.int64)
    outlier_idx = rng.choice(n, min(d["outlier_qty_count"], n), replace=False)
    qty[outlier_idx] = rng.choice([65_535, 80_995, 100_000, 50_000], size=len(outlier_idx))

    day_idx = rng.choice(len(DAY_WEIGHTS), size=n, p=DAY_WEIGHTS)
    dates = pd.date_range(START, SNAPSHOT)[day_idx] + pd.to_timedelta(rng.integers(0, 24 * 60, size=n), unit="m")
    date_str = pd.Series(dates.strftime("%Y-%m-%d %H:%M"), dtype="object")
    fut_idx = _mutate_pct(date_str, d["future_date_pct"])
    date_str.iloc[fut_idx] = (pd.Timestamp("2012-06-10") + pd.to_timedelta(
        rng.integers(0, 15, size=len(fut_idx)), unit="D")).strftime("%Y-%m-%d %H:%M")
    invalid_idx = _mutate_pct(date_str, d["invalid_date_pct"])
    date_str.iloc[invalid_idx] = rng.choice(["2011-13-45 00:00", "not-a-date", "2011-02-30 12:30",
                                             "12/12/2011 09:00"], size=len(invalid_idx))

    stockcode = p_codes[pi].copy().astype(str)
    lc_idx = _mutate_pct(stockcode, d["lowercase_stockcode_pct"])
    stockcode[lc_idx] = np.char.lower(stockcode[lc_idx].astype(str))
    desc_arr = description[pi].copy().astype(object)
    svc_pos = np.where(is_service_row[pi])[0]
    if len(svc_pos):
        desc_arr[svc_pos] = np.nan
    ndesc = _mutate_pct(desc_arr, d["null_description_pct"])
    desc_arr[ndesc] = np.nan

    base_seq = np.arange(chunk_index * CHUNK, chunk_index * CHUNK + n, dtype=np.int64)
    df = pd.DataFrame({
        "invoice": _invoice_array(base_seq),
        "stockcode": pd.Series(stockcode, dtype="string"),
        "description": pd.Series(desc_arr, dtype="string"),
        "quantity": qty,
        "invoice_date": pd.Series(date_str, dtype="object"),
        "unit_price": price,
        "customer_id": cid,
        "country": pd.Series(country, dtype="object"),
        "channel": rng.choice(CHANNELS, size=n, p=[0.6, 0.25, 0.08, 0.07]),
        "promo_id": np.where(rng.random(n) < 0.72, np.nan,
                             rng.integers(1, SCALE["marketing_campaigns"] + 1, size=n).astype(float)),
        "salesperson_id": rng.integers(1, SCALE["salespeople"] + 1, size=n),
    })[SALES_RAW_COLS]

    dup_n = int(n * d["duplicate_rows_pct"] / 100)
    dups_inserted = 0
    if dup_n:
        dups = df.sample(n=dup_n, random_state=_random_dup_seed(chunk_index, "dup"))
        df = pd.concat([df, dups], ignore_index=True)
        dups_inserted = dup_n
    injected = {
        "duplicate_rows": dups_inserted, "negative_price_rows": len(neg_price_idx),
        "zero_price_rows": len(zero_price_idx), "zero_quantity_rows": len(zero_qty_idx),
        "negative_quantity_rows": len(neg_qty_idx), "future_date_rows": len(fut_idx),
        "invalid_date_rows": len(invalid_idx), "lowercase_stockcode_rows": len(lc_idx),
        "outlier_quantity_rows": len(outlier_idx), "null_customer_rows": int((~pick_cust).sum()),
    }
    return df, injected


def generate_sales(rng, products, customers) -> dict:
    path = SYNTHETIC_DIR / "sales_transactions.parquet"
    n_chunks = (SALES_LINES + CHUNK - 1) // CHUNK
    writer, written, injected_totals = None, 0, {}
    for ci in range(n_chunks):
        n_rows = min(CHUNK, SALES_LINES - ci * CHUNK)
        chunk, injected = _sales_chunk(rng, products, customers, ci, n_rows)
        table = pa.Table.from_pandas(chunk, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(path, table.schema)
        writer.write_table(table)
        written += len(chunk)
        for k, v in injected.items():
            injected_totals[k] = injected_totals.get(k, 0) + v
        if ci % 5 == 0 or ci == n_chunks - 1:
            print(f"  sales chunk {ci + 1}/{n_chunks}: {written:,} rows")
    writer.close()
    (SYNTHETIC_DIR / "sales_injected_defects.json").write_text(json.dumps(injected_totals))
    return {"rows": written, "injected": injected_totals}


INVENTORY_WAREHOUSES = ["London DC", "Rotterdam", "Birmingham", "Glasgow", "Manchester", "Bristol"]


def generate_remaining_tables(rng, products, customers, salespeople, campaigns) -> None:
    cust_ids = customers["customer_id"].to_numpy()
    prod_codes = products["product_code"].to_numpy()
    n_sales = SCALE["sales_transactions"]

    returns = pd.DataFrame({
        "return_id": np.arange(1, SCALE["returns"] + 1, dtype=np.int64),
        "invoice": _invoice_array(rng.integers(0, n_sales, size=SCALE["returns"])),
        "product_code": rng.choice(prod_codes, size=SCALE["returns"]),
        "customer_id": rng.choice(cust_ids, size=SCALE["returns"]),
        "return_date": START + pd.to_timedelta(rng.integers(30, TOTAL_DAYS, size=SCALE["returns"]), unit="D"),
        "qty_returned": rng.integers(1, 20, size=SCALE["returns"]),
        "refund_amount": np.round(rng.uniform(2, 80, size=SCALE["returns"]), 2),
        "reason": rng.choice(REFUND_REASONS, size=SCALE["returns"]),
        "disposition": rng.choice(DISPOSITIONS, size=SCALE["returns"], p=[0.6, 0.3, 0.1]),
    })
    returns.to_parquet(SYNTHETIC_DIR / "returns.parquet", index=False)
    print(f"  returns: {len(returns):,}")

    weeks = pd.date_range(pd.Timestamp("2011-01-03"), periods=52, freq="W")
    inv_codes = prod_codes[:66_000]
    grid = pd.DataFrame({
        "product_code": np.repeat(inv_codes, 52),
        "week_starting": np.tile(weeks, len(inv_codes)),
    })
    stock = np.maximum(rng.poisson(6, size=len(grid)) * rng.integers(1, 40, size=len(grid)), 0)
    neg_idx = rng.choice(len(grid), int(len(grid) * INJECT_DEFECTS["inventory"]["negative_stock_pct"] / 100),
                         replace=False)
    stock[neg_idx] = -stock[neg_idx]
    grid["stock_on_hand"] = stock
    grid["reserved"] = rng.integers(0, 20, size=len(grid))
    grid["reorder_point"] = rng.integers(5, 60, size=len(grid))
    grid["on_order"] = rng.integers(0, 30, size=len(grid))
    grid["warehouse"] = rng.choice(INVENTORY_WAREHOUSES, size=len(grid))
    grid.to_parquet(SYNTHETIC_DIR / "inventory_snapshot.parquet", index=False)
    print(f"  inventory_snapshot: {len(grid):,}")

    n_resp = SCALE["campaign_responses"]
    responses = pd.DataFrame({
        "response_id": np.arange(1, n_resp + 1, dtype=np.int64),
        "customer_id": rng.choice(cust_ids, size=n_resp),
        "campaign_id": rng.integers(1, SCALE["marketing_campaigns"] + 1, size=n_resp),
        "response_date": START + pd.to_timedelta(rng.integers(0, TOTAL_DAYS, size=n_resp), unit="D"),
        "channel": rng.choice(CAMPAIGN_CHANNELS, size=n_resp),
        "clicked": rng.random(n_resp) < 0.4,
        "converted": rng.random(n_resp) < 0.12,
    })
    responses.to_parquet(SYNTHETIC_DIR / "campaign_responses.parquet", index=False)
    print(f"  campaign_responses: {len(responses):,}")

    n_t = SCALE["customer_support_tickets"]
    created = START + pd.to_timedelta(rng.integers(0, TOTAL_DAYS, size=n_t), unit="D")
    created = pd.Series(created)
    resolved = created + pd.to_timedelta(rng.integers(0, 10, size=n_t), unit="D")
    priority = rng.choice(PRIORITIES, size=n_t)
    bad_count = min(INJECT_DEFECTS["tickets"]["negative_priority_count"], n_t)
    prio_bad = rng.choice(n_t, bad_count, replace=False)
    priority[prio_bad] = "-1"
    sat = rng.integers(1, 6, size=n_t)
    sat[rng.choice(n_t, min(INJECT_DEFECTS["tickets"]["satisfaction_9_count"], n_t), replace=False)] = 9
    tickets = pd.DataFrame({
        "ticket_id": np.arange(1, n_t + 1, dtype=np.int64),
        "customer_id": rng.choice(cust_ids, size=n_t),
        "created_date": created,
        "resolved_date": resolved,
        "category": rng.choice(TICKET_CATEGORIES, size=n_t),
        "priority": priority,
        "satisfaction": sat,
        "status": rng.choice(["Resolved", "Open", "Escalated", "Closed"], size=n_t,
                             p=[0.6, 0.18, 0.06, 0.16]),
    })
    tickets.to_parquet(SYNTHETIC_DIR / "customer_support_tickets.parquet", index=False)
    print(f"  customer_support_tickets: {len(tickets):,}")

    n_pc = SCALE["price_changes"]
    old = np.round(rng.lognormal(2.4, 0.7, n_pc), 2)
    changes = pd.DataFrame({
        "change_id": np.arange(1, n_pc + 1, dtype=np.int64),
        "product_code": rng.choice(prod_codes, size=n_pc),
        "effective_date": START + pd.to_timedelta(rng.integers(0, TOTAL_DAYS, size=n_pc), unit="D"),
        "old_price": old,
        "new_price": np.round(old * rng.uniform(0.8, 1.25, n_pc), 2),
        "reason": pd.Series(rng.choice(["Category review", "Supplier cost", "Promo", "Competitive",
                                        "Clearance", "Introductory", None], size=n_pc,
                                       p=[0.15, 0.2, 0.2, 0.15, 0.15, 0.1, 0.05]), dtype="object"),
    })
    changes.to_parquet(SYNTHETIC_DIR / "price_changes.parquet", index=False)
    print(f"  price_changes: {len(changes):,}")

    campaigns["budget"] = np.round(rng.uniform(5_000, 500_000, len(campaigns)), 2)
    campaigns["impressions"] = rng.integers(50_000, 5_000_000, len(campaigns))
    campaigns.to_parquet(SYNTHETIC_DIR / "marketing_campaigns.parquet", index=False)
    print(f"  marketing_campaigns: {len(campaigns):,}")
    salespeople.to_parquet(SYNTHETIC_DIR / "salespeople.parquet", index=False)
    print(f"  salespeople: {len(salespeople):,}")


def build_quality_report(injected: dict, sample_n: int = 4_000_000, batch_size: int = 1_000_000) -> dict:
    cols = ["invoice", "stockcode", "quantity", "unit_price", "invoice_date", "customer_id"]
    pf = pq.ParquetFile(SYNTHETIC_DIR / "sales_transactions.parquet")
    total = pf.metadata.num_rows
    stride = max(1, total // sample_n)
    observed = {k: 0 for k in ("invalid_date_rows", "future_date_rows", "negative_quantity_rows",
                               "zero_quantity_rows", "negative_price_rows", "zero_price_rows",
                               "null_customer_rows", "lowercase_stockcode_rows",
                               "outlier_quantity_rows")}
    dup_pool = []
    seen = 0
    for i, batch in enumerate(pf.iter_batches(batch_size=batch_size, columns=cols)):
        df = batch.to_pandas()
        parsed = pd.to_datetime(df["invoice_date"], errors="coerce")
        observed["invalid_date_rows"] += int(parsed.isna().sum())
        observed["future_date_rows"] += int((parsed.dt.normalize() > SNAPSHOT).sum())
        observed["negative_quantity_rows"] += int((df["quantity"] < 0).sum())
        observed["zero_quantity_rows"] += int((df["quantity"] == 0).sum())
        observed["negative_price_rows"] += int((df["unit_price"] < 0).sum())
        observed["zero_price_rows"] += int((df["unit_price"] == 0).sum())
        observed["null_customer_rows"] += int(df["customer_id"].isna().sum())
        observed["lowercase_stockcode_rows"] += int(pd.Series(df["stockcode"]).str.contains(r"[a-z]", regex=True).sum())
        observed["outlier_quantity_rows"] += int((df["quantity"].abs() >= 50000).sum())
        dup_pool.append(df.iloc[::stride])
        seen += len(df)
        if i % 10 == 0:
            print(f"  quality scan {seen:,}/{total:,}")
    sample = pd.concat(dup_pool, ignore_index=True)
    observed["duplicate_rows_detected_in_%d_sample" % len(sample)] = int(sample.duplicated().sum())
    report = {"injected_defects": injected, "observed_defects": observed}
    print("\nInjected vs observed (sales_transactions):")
    for k in injected:
        obs = observed.get(k)
        obs_str = f"{obs:>9,}" if obs is not None else f"{'n/a':>9}"
        print(f"  {k:<36} injected={injected[k]:>9,} observed={obs_str}")
    return report


def summarize() -> dict:
    rows, total = {}, 0
    for path in sorted(SYNTHETIC_DIR.glob("*.parquet")):
        with pq.ParquetFile(path) as pf:
            rows[path.name.replace(".parquet", "")] = {"rows": pf.metadata.num_rows,
                                                       "bytes": path.stat().st_size}
        total += rows[path.name.replace(".parquet", "")]["rows"]
    print(f"\n{'table':<26}{'rows':>12}{'size':>12}")
    for name, r in rows.items():
        print(f"{name:<26}{r['rows']:>12,}{r['bytes'] / 1e6:>10.1f} MB")
    print(f"{'TOTAL':<26}{total:>12,}")
    return {"tables": rows, "total_rows": total}


def generate_all(force: bool = False) -> dict:
    sales_path = SYNTHETIC_DIR / "sales_transactions.parquet"
    inj_path = SYNTHETIC_DIR / "sales_injected_defects.json"
    if sales_path.exists() and inj_path.exists() and not force:
        print("sales data already present (use --force to regenerate)")
        injected = json.loads(inj_path.read_text())
        quality = build_quality_report(injected)
        summary = summarize()
        report = {
            "seed": RANDOM_STATE,
            "tables": summary["tables"],
            "total_rows": summary["total_rows"],
            "quality": quality,
            "generation_seconds": None,
        }
        (SYNTHETIC_DIR / "synthetic_data_quality_report.json").write_text(
            json.dumps(report, indent=2, default=str))
        return report
    t0 = time.perf_counter()
    rng = _rng()
    print("generating customers...")
    customers = generate_customers(rng)
    customers.to_parquet(SYNTHETIC_DIR / "customers.parquet", index=False)
    print(f"  customers: {len(customers):,}")
    print("generating products...")
    products = generate_products(rng)
    products.to_parquet(SYNTHETIC_DIR / "products.parquet", index=False)
    print(f"  products: {len(products):,}")
    print("generating salespeople...")
    salespeople = pd.DataFrame({
        "salesperson_id": np.arange(1, SCALE["salespeople"] + 1, dtype=np.int64),
        "name": rng.choice(FIRST_NAMES, SCALE["salespeople"]) + " " + rng.choice(LAST_NAMES, SCALE["salespeople"]),
        "region": rng.choice(list(COUNTRY_REGION_MAP.values()), SCALE["salespeople"]),
        "manager": rng.choice(FIRST_NAMES, SCALE["salespeople"]) + " " + rng.choice(LAST_NAMES, SCALE["salespeople"]),
        "hire_date": START + pd.to_timedelta(rng.integers(0, TOTAL_DAYS, size=SCALE["salespeople"]), unit="D"),
        "team": rng.choice(["Field", "Key Accounts", "Corp", "Retail"], SCALE["salespeople"]),
        "target_yearly": np.round(rng.uniform(100_000, 1_200_000, SCALE["salespeople"]), 2),
    })
    print("generating marketing campaigns...")
    campaigns = pd.DataFrame({
        "campaign_id": np.arange(1, SCALE["marketing_campaigns"] + 1, dtype=np.int64),
        "name": "Campaign " + rng.integers(1, 9999, SCALE["marketing_campaigns"]).astype(str),
        "channel": rng.choice(CAMPAIGN_CHANNELS, SCALE["marketing_campaigns"]),
        "campaign_type": rng.choice(CAMPAIGN_TYPES, SCALE["marketing_campaigns"]),
        "start_date": START + pd.to_timedelta(rng.integers(0, TOTAL_DAYS - 30, SCALE["marketing_campaigns"]), unit="D"),
    })
    campaigns["end_date"] = campaigns["start_date"] + pd.to_timedelta(
        rng.integers(7, 45, len(campaigns)), unit="D")
    print("generating sales (~40M rows, chunked)...")
    sales_result = generate_sales(rng, products, customers)
    print("generating remaining tables...")
    generate_remaining_tables(rng, products, customers, salespeople, campaigns)
    quality = build_quality_report(sales_result["injected"])
    summary = summarize()
    report = {
        "seed": RANDOM_STATE,
        "tables": summary["tables"],
        "total_rows": summary["total_rows"],
        "quality": quality,
        "generation_seconds": round(time.perf_counter() - t0, 1),
    }
    (SYNTHETIC_DIR / "synthetic_data_quality_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\ndone in {report['generation_seconds']}s")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate ~5 crore synthetic records across 10 tables")
    parser.add_argument("--force", action="store_true", help="regenerate even if data exists")
    args = parser.parse_args()
    generate_all(force=args.force)