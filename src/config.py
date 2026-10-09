from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
SQL_DIR = BASE_DIR / "sql"
FIGURES_DIR = BASE_DIR / "reports" / "figures"
SQL_RESULTS_DIR = PROCESSED_DIR / "sql_results"
POWERBI_DATA_DIR = PROCESSED_DIR / "powerbi"
REPORTS_DIR = BASE_DIR / "reports"
NOTEBOOKS_DIR = BASE_DIR / "notebooks"
SYNTHETIC_DIR = BASE_DIR / "data" / "raw_synthetic"
PROCESSED_SYNTHETIC_DIR = BASE_DIR / "data" / "processed_synthetic"

for _dir in (RAW_DIR, PROCESSED_DIR, SQL_DIR, FIGURES_DIR, SQL_RESULTS_DIR, POWERBI_DATA_DIR, REPORTS_DIR,
             SYNTHETIC_DIR, PROCESSED_SYNTHETIC_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

RAW_ZIP = RAW_DIR / "online_retail_ii.zip"
RAW_CSV = RAW_DIR / "online_retail_ii.csv"

DB_NAME = "enterprise_sales"
DB_USER = "postgres"
DB_HOST = "localhost"
DB_PORT = 5432
DB_URL = f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

CURRENCY = "GBP"
CHURN_INACTIVITY_DAYS = 90
RISK_THRESHOLDS = {"high": 0.66, "medium": 0.33}
RANDOM_STATE = 42

SERVICE_CODES = {
    "POST", "DOT", "M", "D", "S", "BANK CHARGES", "ADJUST", "ADJUST2",
    "AMAZONFEE", "PADS", "CRUK", "B", "m", "GIFT",
}

COUNTRY_REGION_MAP = {
    "United Kingdom": "United Kingdom",
    "EIRE": "Europe", "Germany": "Europe", "France": "Europe",
    "Netherlands": "Europe", "Spain": "Europe", "Switzerland": "Europe",
    "Belgium": "Europe", "Portugal": "Europe", "Italy": "Europe",
    "Norway": "Europe", "Sweden": "Europe", "Cyprus": "Europe",
    "Finland": "Europe", "Austria": "Europe", "Denmark": "Europe",
    "Greece": "Europe", "Poland": "Europe", "Malta": "Europe",
    "Iceland": "Europe", "Lithuania": "Europe", "Czech Republic": "Europe",
    "Channel Islands": "Europe", "European Community": "Europe",
    "USA": "Americas", "Canada": "Americas", "Brazil": "Americas",
    "Bermuda": "Americas", "West Indies": "Americas",
    "Australia": "Asia Pacific", "Japan": "Asia Pacific",
    "Hong Kong": "Asia Pacific", "Singapore": "Asia Pacific",
    "Thailand": "Asia Pacific", "Korea": "Asia Pacific",
    "Israel": "Middle East & Africa", "United Arab Emirates": "Middle East & Africa",
    "Bahrain": "Middle East & Africa", "Nigeria": "Middle East & Africa",
    "Saudi Arabia": "Middle East & Africa", "Lebanon": "Middle East & Africa",
    "RSA": "Middle East & Africa",
    "Unspecified": "Unknown",
}

COUNTRY_ISO_MAP = {
    "EIRE": "IE", "United Kingdom": "GB", "USA": "US", "RSA": "ZA",
    "European Community": "EU", "West Indies": "WI", "Korea": "KR",
    "Channel Islands": "GB", "Unspecified": "XX",
}

CATEGORY_RULES = [
    ("Christmas & Seasonal", ["CHRISTMAS", "XMAS", "ADVENT", "SANTA", "REINDEER", "T-LIGHT", "TEALIGHT", "LIGHT HOLDER"]),
    ("Lighting", ["LIGHT", "LAMP", "CANDLE", "LUMINAIRE"]),
    ("Bags & Travel", ["BAG", "SHOPPING", "TOTE", "JEWELLERY BOX", "TOILET"]),
    ("Drinkware", ["MUG", "CUP", "TEAPOT", "FLASK", "BOTTLE", "BEAKER", "GLASS"]),
    ("Kitchen & Dining", ["PLATE", "BOWL", "DISH", "TRAY", "CUTLERY", "KNIFE", "FORK", "SPOON", "SAUCER", "CAKE STAND", "CUTTING BOARD", "JUG"]),
    ("Home Décor", ["FRAME", "MIRROR", "HOOK", "WALL ART", "ORNAMENT", "VASE", "BIRDHOUSE", "CLOCK", "MIRROR"]),
    ("Stationery & Gifting", ["CARD", "WRAP", "PAPER", "NOTEBOOK", "GIFT BAG", "TAG", "ENVELOPE", "STAMP", "PENCIL"]),
    ("Bath & Storage", ["BATH", "SOAP", "TOWEL", "CABINET", "BASKET", "DRAWER", "HANGER", "ORGANISER", "LAUNDRY"]),
    ("Toys & Games", ["TOY", "GAME", "DOLL", "PUZZLE", "TEDDY", "PLAYHOUSE", "DINOSAUR", "KIDS"]),
    ("Garden & Outdoor", ["GARDEN", "PLANT", "BIRD", "OUTDOOR", "PATIO"]),
    ("Textiles & Soft Furnishings", ["CUSHION", "BLANKET", "THROW", "CUSHION", "CHARM"]),
    ("Jewellery & Accessories", ["NECKLACE", "BRACELET", "EARRING", "RING", "WATCH", "CHARM", "BANGLE"]),
    ("Junk Mail & Freebies", ["FREE", "SAMPLE", "COMMISSION", "DAMAGES", "DOTCOM"]),
]

SERVICE_CATEGORY_RULES = {
    "POST": "Postage & Delivery",
    "DOT": "Postage & Delivery",
    "M": "Manual Adjustments",
    "ADJUST": "Manual Adjustments",
    "ADJUST2": "Manual Adjustments",
    "BANK CHARGES": "Bank Charges",
    "AMAZONFEE": "Marketplace Fees",
    "CRUK": "Charity Donation",
    "D": "Discounts & Giveaways",
    "S": "Samples & Giveaways",
    "B": "Samples & Giveaways",
    "m": "Manual Adjustments",
    "GIFT": "Gift Vouchers",
    "PADS": "Packing & Fixings",
}

SEGMENT_PROFILES = {
    "Champions": "Bought recently, buy often, spend the most",
    "Loyal Customers": "Consistent repeat buyers with strong spend",
    "Potential Loyalists": "Recent buyers showing increasing frequency",
    "New Customers": "First purchase within the last 90 days",
    "At Risk": "Valuable customers whose recency is deteriorating",
    "Hibernating": "Low activity, long overdue, low value",
    "Lost": "No purchase for more than 180 days with weak history",
    "Big Spenders": "High monetary value but irregular or cooling engagement",
}
