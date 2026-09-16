import json
from decimal import Decimal, ROUND_HALF_UP
from urllib.request import Request, urlopen

API_URL = "https://oilprices.pk/api/latest"
CONFIG_FILE = "config.json"

PRODUCT_IDS = {
    "Motor Spirit (Petrol)": "petrol",
    "High Speed Diesel (HSD)": "hsd",
    "Liquefied Petroleum Gas (LPG)": "lpg",
    "Superior Kerosene Oil (SKO)": "kerosene",
}


def money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


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

if not isinstance(api_data, dict) or not isinstance(api_data.get("products"), list):
    raise ValueError("API response must contain a products array")

api_date = str(api_data.get("effectiveDate", ""))[:10]
if not api_date:
    raise ValueError("API response does not contain effectiveDate")

api_products = {}
for item in api_data["products"]:
    if not isinstance(item, dict):
        continue
    product_id = PRODUCT_IDS.get(item.get("product"))
    if product_id is None:
        continue
    if item.get("pricePkr") is None:
        raise ValueError(f"Missing pricePkr for {item.get('product')}")
    api_products[product_id] = money(item["pricePkr"])

if not api_products:
    raise ValueError("No supported products found in API response")

with open(CONFIG_FILE, encoding="utf-8") as file:
    config = json.load(file)

changed = False
for product_id, new_price in api_products.items():
    product = config["products"].get(product_id)
    if product is None:
        continue

    old_price = money(product["current_price"])
    if new_price != old_price:
        product["previous_price"] = float(old_price)
        product["current_price"] = float(new_price)

        price_change = new_price - old_price
        product["price_change"] = float(price_change)
        product["price_change_percentage"] = float(
            (price_change / old_price * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        changed = True

    # Save date metadata even when the price itself is unchanged.
    if (
        product.get("last_change_date") != api_date
        or product.get("effective_date") != api_date
    ):
        changed = True
    product["last_change_date"] = api_date
    product["effective_date"] = api_date

new_last_updated = f"{api_date}T00:00:00+05:00"
if config.get("last_updated") != new_last_updated:
    changed = True
    config["last_updated"] = new_last_updated

if changed:
    with open(CONFIG_FILE, "w", encoding="utf-8", newline="\n") as file:
        json.dump(config, file, indent=2, ensure_ascii=False)
        file.write("\n")
    print("config.json updated.")
else:
    print("No price changes found.")
