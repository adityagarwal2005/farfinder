"""
flights.py — Travelpayouts / Aviasales Data API wrapper

Token: set env var TRAVELPAYOUTS_TOKEN  (or it defaults to the hardcoded key)

Endpoints used:
  /v1/prices/cheap              — cheapest per stop-count for a month
  /v1/prices/direct             — non-stop only
  /v1/prices/calendar           — price per calendar day
  /v1/prices/monthly            — cheapest month per route
  /aviasales/v3/get_latest_prices — latest cached prices with date info
  /aviasales/v3/search_by_price_range — find routes within a budget
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import requests

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────────────

TP_TOKEN = os.getenv("TRAVELPAYOUTS_TOKEN", "9f5646b1e8ffe0f51ba473251ab857c6")
BASE     = "https://api.travelpayouts.com"
HEADERS  = {"x-access-token": TP_TOKEN}

AIRLINES: dict[str, str] = {
    "6E": "IndiGo",       "SG": "SpiceJet",    "AI": "Air India",
    "UK": "Vistara",      "IX": "AirAsia India","QP": "Akasa Air",
    "G8": "GoFirst",      "EK": "Emirates",     "QR": "Qatar Airways",
    "EY": "Etihad",       "SQ": "Singapore Air","BA": "British Airways",
    "LH": "Lufthansa",    "FZ": "flydubai",     "WY": "Oman Air",
    "TK": "Turkish Airlines","AF": "Air France", "KL": "KLM",
    "MH": "Malaysia Air", "TG": "Thai Airways", "CX": "Cathay Pacific",
}

STOPS_LABEL = {0: "Non-stop", 1: "1 Stop", 2: "2 Stops"}


def _airline_name(code: str) -> str:
    return AIRLINES.get(code.upper(), code)


def _get(endpoint: str, params: dict) -> dict | None:
    """Shared GET helper. Returns parsed JSON or None on failure."""
    try:
        r = requests.get(
            f"{BASE}{endpoint}",
            headers=HEADERS,
            params={**params, "token": TP_TOKEN},
            timeout=15,
        )
        if r.status_code in (400, 404, 422):
            return None
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            return None
        return data
    except requests.RequestException as e:
        print(f"⚠️  TP API error [{endpoint}]: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  1. CHEAP TICKETS  (cheapest by stop count for a month)
# ─────────────────────────────────────────────────────────────────────────────

def search_cheap(
    origin: str, dest: str, depart_date: str, currency: str = "inr"
) -> list[dict]:
    """
    Returns cheapest offers per stop-count for the given month.
    depart_date: YYYY-MM-DD  (only year-month is used)
    """
    month = depart_date[:7]
    data = _get("/v1/prices/cheap", {
        "origin": origin.upper(), "destination": dest.upper(),
        "depart_date": month, "currency": currency,
    })
    if not data:
        return []

    results = []
    dest_data = data["data"].get(dest.upper(), {})
    for stop_key, info in dest_data.items():
        price = info.get("price", 0)
        if price <= 0:
            continue
        carrier = info.get("airline", "")
        departure_at = info.get("departure_at", "")
        # Parse depart date from the field
        dep_date = ""
        if departure_at:
            try:
                dep_date = departure_at[:10]
            except Exception:
                pass
        results.append({
            "price_inr":    price,
            "carrier":      _airline_name(carrier),
            "carrier_code": carrier,
            "stops":        int(stop_key),
            "stops_label":  STOPS_LABEL.get(int(stop_key), f"{stop_key} stops"),
            "departure_at": departure_at,
            "dep_date":     dep_date,
            "duration_min": 0,
            "duration_fmt": "—",
            "legs":         [],
            "source":       "cheap",
        })

    results.sort(key=lambda x: x["price_inr"])
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  2. DIRECT (NON-STOP ONLY)
# ─────────────────────────────────────────────────────────────────────────────

def search_direct(
    origin: str, dest: str, depart_date: str, currency: str = "inr"
) -> list[dict]:
    """Returns cheapest non-stop tickets for the month."""
    month = depart_date[:7]
    data = _get("/v1/prices/direct", {
        "origin": origin.upper(), "destination": dest.upper(),
        "depart_date": month, "currency": currency,
    })
    if not data:
        return []

    results = []
    dest_data = data["data"].get(dest.upper(), {})
    for stop_key, info in dest_data.items():
        price = info.get("price", 0)
        if price <= 0:
            continue
        results.append({
            "price_inr":    price,
            "carrier":      _airline_name(info.get("airline", "")),
            "carrier_code": info.get("airline", ""),
            "stops":        0,
            "stops_label":  "Non-stop",
            "departure_at": info.get("departure_at", ""),
            "dep_date":     info.get("departure_at", "")[:10],
            "duration_min": 0,
            "duration_fmt": "—",
            "legs":         [],
            "source":       "direct",
        })
    results.sort(key=lambda x: x["price_inr"])
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  3. LATEST PRICES  (v3 — with actual depart dates)
# ─────────────────────────────────────────────────────────────────────────────

def get_latest_prices(
    origin: str, dest: str, currency: str = "inr", limit: int = 10
) -> list[dict]:
    """
    Get latest cached prices with actual departure dates.
    Useful when cheap/direct returns empty.
    """
    data = _get("/aviasales/v3/get_latest_prices", {
        "origin":              origin.upper(),
        "destination":         dest.upper(),
        "currency":            currency,
        "period_type":         "day",
        "show_to_affiliates":  "true",
        "sorting":             "price",
        "one_way":             "true",
        "limit":               limit,
    })
    if not data or not data.get("data"):
        return []

    results = []
    for item in data["data"]:
        price = item.get("value", 0)
        if price <= 0:
            continue
        carrier = item.get("airline", "")
        stops = item.get("number_of_changes", 0)
        results.append({
            "price_inr":    price,
            "carrier":      _airline_name(carrier),
            "carrier_code": carrier,
            "stops":        stops,
            "stops_label":  STOPS_LABEL.get(stops, f"{stops} stops"),
            "departure_at": item.get("departure_at", ""),
            "dep_date":     item.get("depart_date", ""),
            "duration_min": item.get("duration", 0) or 0,
            "duration_fmt": _fmt_dur(item.get("duration", 0) or 0),
            "legs":         [],
            "source":       "latest",
        })
    results.sort(key=lambda x: x["price_inr"])
    return results


def _fmt_dur(minutes: int) -> str:
    if not minutes:
        return "—"
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h else f"{m}m"


# ─────────────────────────────────────────────────────────────────────────────
#  4. PRICE CALENDAR  (price per calendar day for a month)
# ─────────────────────────────────────────────────────────────────────────────

def get_price_calendar(
    origin: str, dest: str, month: str, currency: str = "inr"
) -> dict[str, dict]:
    """
    Returns {date_str: {price, airline, stops}} for every day with data.
    month format: YYYY-MM
    """
    data = _get("/v1/prices/calendar", {
        "origin":        origin.upper(),
        "destination":   dest.upper(),
        "month":         month,
        "calendar_type": "departure_date",
        "currency":      currency,
    })
    if not data or not data.get("data"):
        return {}

    calendar: dict[str, dict] = {}
    for date_str, info in data["data"].items():
        price = info.get("price", 0)
        if price > 0:
            carrier = info.get("airline", "")
            calendar[date_str] = {
                "price":        price,
                "airline":      _airline_name(carrier),
                "airline_code": carrier,
                "stops":        info.get("transfers", 0),
            }
    return calendar


# ─────────────────────────────────────────────────────────────────────────────
#  5. FLEXIBLE DATE SEARCH  (±N days, find cheapest window)
# ─────────────────────────────────────────────────────────────────────────────

def search_flexible(
    origin: str, dest: str, target_date: str,
    flex_days: int = 3, currency: str = "inr"
) -> list[dict]:
    """
    Search ±flex_days around target_date.
    Returns list of {date, price, airline, stops, days_diff, is_target}
    sorted cheapest first.
    """
    td    = datetime.strptime(target_date, "%Y-%m-%d").date()
    month = td.strftime("%Y-%m")

    # Build combined calendar (may span two months)
    calendar = get_price_calendar(origin, dest, month, currency)
    if flex_days >= 15:
        # Could span next month
        next_month = (td + timedelta(days=30)).strftime("%Y-%m")
        calendar.update(get_price_calendar(origin, dest, next_month, currency))

    results = []
    for offset in range(-flex_days, flex_days + 1):
        check = td + timedelta(days=offset)
        if check < date.today():
            continue
        dstr = check.strftime("%Y-%m-%d")
        if dstr in calendar:
            entry = calendar[dstr]
            results.append({
                "date":       dstr,
                "days_diff":  offset,
                "is_target":  offset == 0,
                "price":      entry["price"],
                "airline":    entry["airline"],
                "stops":      entry["stops"],
                "label":      "Today" if offset == 0
                              else f"+{offset}d" if offset > 0
                              else f"{offset}d",
            })

    results.sort(key=lambda x: x["price"])
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  6. MONTHLY CHEAPEST  (find cheapest month to fly a route)
# ─────────────────────────────────────────────────────────────────────────────

def get_monthly_cheapest(
    origin: str, dest: str, currency: str = "inr"
) -> list[dict]:
    """Returns cheapest price per month for the next 6 months."""
    data = _get("/v1/prices/monthly", {
        "origin": origin.upper(), "destination": dest.upper(),
        "currency": currency,
    })
    if not data or not data.get("data"):
        return []

    results = []
    for month_str, info in data["data"].items():
        price = info.get("price", 0)
        if price > 0:
            carrier = info.get("airline", "")
            results.append({
                "month":    month_str,
                "price":    price,
                "airline":  _airline_name(carrier),
                "stops":    info.get("transfers", 0),
            })
    results.sort(key=lambda x: x["month"])
    return results[:8]


# ─────────────────────────────────────────────────────────────────────────────
#  7. BUDGET SEARCH  (find destinations from city within a price range)
# ─────────────────────────────────────────────────────────────────────────────

def search_by_budget(
    origin: str,
    budget_min: int = 0,
    budget_max: int = 5000,
    currency: str = "inr",
    direct_only: bool = False,
    limit: int = 20,
) -> list[dict]:
    """
    Find all destinations reachable from origin within the budget.
    Returns list of {destination, price, airline, stops, depart_date}.
    """
    data = _get("/aviasales/v3/search_by_price_range", {
        "origin":              origin.upper(),
        "destination":         "-",       # all destinations
        "value_min":           budget_min,
        "value_max":           budget_max,
        "one_way":             "true",
        "direct":              "true" if direct_only else "false",
        "currency":            currency,
        "locale":              "en",
        "limit":               limit,
        "page":                1,
    })
    if not data or not data.get("data"):
        return []

    results = []
    for item in data["data"]:
        carrier = item.get("airline", "")
        results.append({
            "destination":      item.get("destination_name", item.get("destination_code", "")),
            "destination_iata": item.get("destination_code", ""),
            "price":            item.get("value", 0),
            "airline":          _airline_name(carrier),
            "airline_code":     carrier,
            "stops":            item.get("number_of_changes", 0),
            "depart_date":      item.get("departure_at", "")[:10],
            "duration_min":     item.get("duration", 0) or 0,
        })
    results.sort(key=lambda x: x["price"])
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  8. PRICE TREND CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

def classify_price_trend(
    origin: str, dest: str, current_price: int, currency: str = "inr"
) -> dict:
    """
    Compare current_price to the monthly cheapest over the last 3 months.
    Returns: {trend, label, pct_diff}
    """
    try:
        monthly = get_monthly_cheapest(origin, dest, currency)
        if not monthly:
            return {"trend": "unknown", "label": "—", "pct_diff": 0}
        prices = [m["price"] for m in monthly]
        avg = sum(prices) / len(prices)
        pct = round((current_price - avg) / avg * 100, 1)
        if pct <= -15:
            return {"trend": "cheap",     "label": f"🟢 {abs(pct)}% below avg", "pct_diff": pct}
        elif pct >= 15:
            return {"trend": "expensive", "label": f"🔴 {pct}% above avg",      "pct_diff": pct}
        else:
            return {"trend": "normal",    "label": f"🟡 Near avg price",        "pct_diff": pct}
    except Exception:
        return {"trend": "unknown", "label": "—", "pct_diff": 0}


# ─────────────────────────────────────────────────────────────────────────────
#  BOOKING DEEP LINKS
# ─────────────────────────────────────────────────────────────────────────────

def build_booking_link(
    origin: str, dest: str, depart_date: str, adults: int = 1
) -> dict[str, str]:
    """Generate deep links to popular booking sites."""
    date_mmddyy = ""
    try:
        d = datetime.strptime(depart_date, "%Y-%m-%d")
        date_mmddyy = d.strftime("%m/%d/%y")
        date_skyscanner = d.strftime("%Y-%m-%d")
        date_mmt = d.strftime("%d/%m/%Y")
    except Exception:
        date_skyscanner = depart_date
        date_mmt = ""

    return {
        "skyscanner": (
            f"https://www.skyscanner.co.in/transport/flights/{origin.lower()}/{dest.lower()}/"
            f"{date_skyscanner.replace('-', '')}/?"
            f"adults={adults}&currency=INR"
        ),
        "makemytrip": (
            f"https://www.makemytrip.com/flight/search?"
            f"itinerary={origin.upper()}-{dest.upper()}-{date_mmt}&tripType=O&paxType=A-{adults}_C-0_I-0"
        ),
        "goibibo": (
            f"https://www.goibibo.com/flights/search/"
            f"?src={origin.upper()}&dst={dest.upper()}&date={depart_date.replace('-', '')}"
            f"&adults={adults}&children=0&infants=0&class=e&seType=SR"
        ),
        "cleartrip": (
            f"https://www.cleartrip.com/flights/results?"
            f"from={origin.upper()}&to={dest.upper()}&depart_date={depart_date}"
            f"&adults={adults}&childs=0&infants=0&class=Economy&intl=n&page=loaded"
        ),
    }
