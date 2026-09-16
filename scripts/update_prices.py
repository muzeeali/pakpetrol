import json
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_URL = "https://oilprices.pk/api/latest"
CONFIG_FILE = "config.json"
PKT = ZoneInfo("Asia/Karachi")

ALIASES = {
    "petrol": ["petrol", "motor spirit", "super petrol"],
    "hsd": ["hsd", "high speed diesel", "diesel"],
    "kerosene": ["kerosene"],
    "ldo": ["ldo", "light diesel"],
    "lpg": ["lpg", "auto lpg"],
    "cng": ["cng"],
}


def clean(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def get_records(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("data", "prices", "results", "latest"):
            if isinstance(data.get(key), list):
                return data[key]

        if "product" in data or "pricePkr" in data or "price" in data:
            return [data]

    raise ValueError("Unexpected API response format")


def get_product_name(record):
    return clean(
        record.get("product")
        or record.get("productName")
        or record.get("name")
        or record.get("product_id")
        or record.get("productId")
        or ""
    )


def get_price(record):
    for key in ("pricePkr", "price", "current_price", "currentPrice"):
        if record.get(key) is not None:
            return money(record[key])
    return None


def get_date(record, fallback):
    return str(
        record.get("effectiveDate")
        or record.get("effective_date")
        or record.get("date")
        or fallback
    )[:10]


def find_record(records, product_id):
    for record in records:
        name = get_product_name(record)

        if any(alias in name for alias in ALIASES[product_id]):
            return record

    return None


request = Request(
    API_URL,
    headers={
        "Accept": "application/json",
        "User-Agent": "pakpetrol-price-updater/1.0",
    },
)

with urlopen(request, timeout=30) as response:
    if response.status != 200:
        raise RuntimeError(f"API returned HTTP {response.status}")

    api_data = json.load(response)

with open(CONFIG_FILE, encoding="utf-8") as file:
    config = json.load(file)

records = get_records(api_data)
now = datetime.now(PKT)
today = now.date().isoformat()
changed = False
matched = 0

for product_id, product in config["products"].items():
    record = find_record(records, product_id)

    if record is None:
        continue

    matched += 1
    new_price = get_price(record)
    old_price = money(product["current_price"])

    if new_price is None or new_price <= 0:
        raise ValueError(f"Invalid API price for {product_id}")

    if new_price == old_price:
        continue

    # Preserve the old current price as the new previous price.
    product["previous_price"] = float(old_price)
    product["current_price"] = float(new_price)

    difference = new_price - old_price
    percentage = (difference / old_price * 100).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    product["price_change"] = float(difference)
    product["price_change_percentage"] = float(percentage)

    effective_date = get_date(record, today)
    product["last_change_date"] = effective_date
    product["effective_date"] = effective_date

    changed = True

if matched == 0:
    raise ValueError("No configured products matched the API response")

if changed:
    config["last_updated"] = now.isoformat(timespec="seconds")

    with open(CONFIG_FILE, "w", encoding="utf-8", newline="\n") as file:
        json.dump(config, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print("config.json updated.")
else:
    print("No price changes found.")
