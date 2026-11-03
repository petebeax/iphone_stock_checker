"""Apple Canada product-variant discovery and nearby pickup availability.

Apple's endpoints are undocumented and may change without notice.
No Streamlit imports here, so scheduled checks work without a browser.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import urlparse

import requests

BASE = "https://www.apple.com"
MARKET = "ca"
FAMILIES = {
    "iPhone 18 Pro / Pro Max": "iphone-18-pro",
    "iPhone Duo": "iphone-duo",
}
PICKUP_PATH = "/shop/retail/pickup-message"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
CATALOG_RE = re.compile(
    r'"partNumber":"(?P<part>[^"\\]+)",'
    r'"price":\{"fullPrice":[\d.]+\},'
    r'"category":"iphone","name":"(?P<name>[^"\\]+)"'
)
NAME_RE = re.compile(
    r"^(iPhone (?:18 Pro Max|18 Pro|Duo))\s+(\d+(?:GB|TB))\s+(.+)$",
    re.IGNORECASE,
)
PART_RE = re.compile(r"[A-Z0-9][A-Z0-9/-]{3,30}", flags=re.I)


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en-CA,en;q=0.9"})
    return session


def buy_url(family: str) -> str:
    return f"{BASE}/{MARKET}/shop/buy-iphone/{family}"


def family_for_model(model: str) -> str:
    return FAMILIES["iPhone Duo" if "Duo" in model else "iPhone 18 Pro / Pro Max"]


def parse_catalog_html(html: str) -> list[dict[str, str]]:
    result = {}
    normalized = html.replace("\\u00a0", " ").replace("\u00a0", " ")
    for match in CATALOG_RE.finditer(normalized):
        name = " ".join(match.group("name").split())
        parsed = NAME_RE.match(name)
        if not parsed:
            continue
        model, storage, color = parsed.groups()
        part = match.group("part")
        result[part] = {
            "part": part,
            "model": model,
            "storage": storage.upper(),
            "color": color.strip(),
        }
    return list(result.values())


def get_catalog() -> list[dict[str, str]]:
    session = new_session()
    variants = {}
    errors = []
    for family in FAMILIES.values():
        try:
            response = session.get(buy_url(family), timeout=18)
            response.raise_for_status()
            found = parse_catalog_html(response.text)
            if not found:
                errors.append(f"No variants found on {family} page")
            for item in found:
                variants[item["part"]] = item
        except requests.RequestException as exc:
            errors.append(f"{family}: {exc}")
    if not variants:
        raise RuntimeError("Unable to load Apple's iPhone catalog. " + "; ".join(errors))
    return list(variants.values())


def storage_sort_key(storage: str) -> int:
    m = re.fullmatch(r"(\d+)(GB|TB)", storage, flags=re.I)
    return int(m[1]) * (1024 if m[2].upper() == "TB" else 1) if m else 0


def variants_for_model(catalog: list[dict], model: str, storage: str | None = None) -> list[dict]:
    return [v for v in catalog if v["model"] == model and (storage is None or v["storage"] == storage)]


def classify_pickup(display: str | None) -> str:
    value = (display or "").strip().lower()
    if value == "available":
        return "Available"
    if value in {"unavailable", "not available", "not_available", "out of stock", "nostock"}:
        return "Unavailable"
    return "Unknown"


def secure_apple_link(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        return None
    if parsed.hostname != "apple.com" and not parsed.hostname.endswith(".apple.com"):
        return None
    return parsed._replace(scheme="https").geturl()


def store_identifier(store: dict) -> str:
    """Use Apple's store number, falling back to a stable visible name/city."""
    number = store.get("storeNumber") or store.get("storeId")
    if number is not None:
        return str(number)
    name = str(store.get("storeName") or "Unknown store").strip().casefold()
    city = str(store.get("city") or "").strip().casefold()
    return f"{name}|{city}"


def check_pickup(part: str, location: str, family: str) -> tuple[list[dict], str]:
    """Live query. The Streamlit UI adds its own short TTL cache."""
    if not PART_RE.fullmatch(part):
        raise ValueError("Invalid Apple part number")
    if family not in FAMILIES.values():
        raise ValueError("Invalid Apple product family")
    location = location.strip()
    if not location or len(location) > 100:
        raise ValueError("Invalid location")
    session = new_session()
    referer = buy_url(family)
    warm = session.get(referer, timeout=18)
    warm.raise_for_status()
    response = session.get(
        f"{BASE}/{MARKET}{PICKUP_PATH}",
        params={"pl": "true", "mts.0": "regular", "parts.0": part, "location": location},
        headers={
            "Accept": "application/json",
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=18,
    )
    if response.status_code in (429, 541):
        raise RuntimeError("Apple rate-limited the request. Stop checking for 15–30 minutes.")
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("Apple returned a non-JSON response.") from exc
    stores = data.get("body", {}).get("stores")
    if not isinstance(stores, list):
        raise RuntimeError("Apple's pickup response changed (missing body.stores).")

    output = []
    for store in stores:
        item = (store.get("partsAvailability") or {}).get(part) or {}
        quote = (item.get("messageTypes") or {}).get("regular") or {}
        message = quote.get("storePickupQuote") or item.get("pickupSearchQuote") or ""
        message = re.sub(r"<[^>]+>", " ", str(message))
        message = " ".join(message.split())
        output.append({
            "Store ID": store_identifier(store),
            "Store": store.get("storeName") or "Unknown store",
            "City": store.get("city") or "",
            "Distance": store.get("storeDistanceWithUnit") or "",
            "Status": classify_pickup(item.get("pickupDisplay")),
            "Pickup details": message,
            "Apple link": secure_apple_link(
                store.get("makeReservationUrl") or store.get("reservationUrl")
            ),
        })
    output.sort(key=lambda s: {"Available": 0, "Unavailable": 1, "Unknown": 2}[s["Status"]])
    return output, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
