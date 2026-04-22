"""
airports.py — Airport discovery, geocoding, ground transport

Data sources (all free, no key needed):
  - OpenFlights airports.dat  : 7 000+ airports with IATA codes
  - Nominatim (OpenStreetMap) : geocoding city names → lat/lon
"""

from __future__ import annotations

import csv
import io
import math
import threading
import requests

# ─────────────────────────────────────────────────────────────────────────────
#  KNOWN INDIAN IATA CODES  (fast lookup without API call)
# ─────────────────────────────────────────────────────────────────────────────

INDIA_IATA: dict[str, str] = {
    # Major metros
    "delhi": "DEL", "new delhi": "DEL", "dilli": "DEL",
    "mumbai": "BOM", "bombay": "BOM",
    "bangalore": "BLR", "bengaluru": "BLR",
    "hyderabad": "HYD",
    "chennai": "MAA", "madras": "MAA",
    "kolkata": "CCU", "calcutta": "CCU",
    "ahmedabad": "AMD",
    "pune": "PNQ",
    "kochi": "COK", "cochin": "COK",
    "goa": "GOI",
    # Tier-2
    "jaipur": "JAI",
    "lucknow": "LKO",
    "varanasi": "VNS",
    "agra": "AGR",
    "bhopal": "BHO",
    "indore": "IDR",
    "nagpur": "NAG",
    "chandigarh": "IXC",
    "amritsar": "ATQ",
    "srinagar": "SXR",
    "jammu": "IXJ",
    "leh": "IXL",
    "dehradun": "DED",
    "patna": "PAT",
    "ranchi": "IXR",
    "bhubaneswar": "BBI",
    "raipur": "RPR",
    "visakhapatnam": "VTZ", "vizag": "VTZ",
    "coimbatore": "CJB",
    "madurai": "IXM",
    "trichy": "TRZ", "tiruchirappalli": "TRZ",
    "thiruvananthapuram": "TRV", "trivandrum": "TRV",
    "calicut": "CCJ", "kozhikode": "CCJ",
    "mangalore": "IXE",
    "hubli": "HBX",
    "belgaum": "IXG",
    "port blair": "IXZ",
    "dibrugarh": "DIB",
    "guwahati": "GAU",
    "imphal": "IMF",
    "bagdogra": "IXB", "siliguri": "IXB",
    "udaipur": "UDR",
    "jodhpur": "JDH",
    "aurangabad": "IXU",
    "shirdi": "SAG",
    "surat": "STV",
    "vadodara": "BDQ",
    "rajkot": "RAJ",
    "bhavnagar": "BHU",
    "jabalpur": "JLR",
    "gorakhpur": "GOP",
    "allahabad": "IXD", "prayagraj": "IXD",
    "gwalior": "GWL",
    "tirupati": "TIR",
    "vijayawada": "VGA",
    # International hubs commonly used from India
    "dubai": "DXB",
    "singapore": "SIN",
    "bangkok": "BKK",
    "london": "LHR",
    "new york": "JFK",
    "toronto": "YYZ",
    "sydney": "SYD",
    "kuala lumpur": "KUL",
    "abu dhabi": "AUH",
    "doha": "DOH",
}


def city_to_iata(city: str) -> str | None:
    """Fast lookup for known cities before hitting any API."""
    return INDIA_IATA.get(city.lower().strip())


# ─────────────────────────────────────────────────────────────────────────────
#  OPENFLIGHTS DATABASE
# ─────────────────────────────────────────────────────────────────────────────

AIRPORTS_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
)

_airports_cache: list | None = None
_cache_lock = threading.Lock()


def load_airports() -> list[dict]:
    """Download & cache OpenFlights airport database (once per process)."""
    global _airports_cache
    with _cache_lock:
        if _airports_cache is not None:
            return _airports_cache

        try:
            r = requests.get(AIRPORTS_URL, timeout=20)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"⚠️  Airport DB unavailable: {e}")
            _airports_cache = []
            return []

        airports: list[dict] = []
        for row in csv.reader(io.StringIO(r.text)):
            try:
                if len(row) < 9:
                    continue
                iata = row[4].strip().strip('"')
                if not iata or iata == r"\N" or len(iata) != 3:
                    continue
                airports.append({
                    "name":    row[1].strip().strip('"'),
                    "city":    row[2].strip().strip('"'),
                    "country": row[3].strip().strip('"'),
                    "iata":    iata,
                    "lat":     float(row[6].strip().strip('"')),
                    "lon":     float(row[7].strip().strip('"')),
                })
            except (ValueError, IndexError):
                continue

        _airports_cache = airports
        print(f"✅  Airport DB: {len(airports)} airports loaded")
        return _airports_cache


# ─────────────────────────────────────────────────────────────────────────────
#  GEOCODING
# ─────────────────────────────────────────────────────────────────────────────

def geocode_location(query: str) -> tuple[float, float] | None:
    """Convert a city/place name → (lat, lon) via Nominatim. Free, no key."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "FarFinder/2.0 (flight-agent)"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"⚠️  Geocode failed for '{query}': {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  HAVERSINE
# ─────────────────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─────────────────────────────────────────────────────────────────────────────
#  RADIUS SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def find_airports_in_radius(
    lat: float, lon: float,
    radius_km: float,
    max_results: int = 15,
) -> list[dict]:
    """Return airports within radius_km, sorted by distance. Includes distance_km."""
    nearby = []
    for ap in load_airports():
        d = haversine(lat, lon, ap["lat"], ap["lon"])
        if d <= radius_km:
            nearby.append({**ap, "distance_km": round(d, 1)})
    nearby.sort(key=lambda x: x["distance_km"])
    return nearby[:max_results]


# ─────────────────────────────────────────────────────────────────────────────
#  DESTINATION RESOLVER
# ─────────────────────────────────────────────────────────────────────────────

def resolve_destination_airport(destination: str) -> dict | None:
    """
    Find the primary airport serving a destination city.
    Returns airport dict with distance_km from the city centre.
    """
    coords = geocode_location(destination)
    if not coords:
        return None
    lat, lon = coords
    for radius in (60, 150, 350):
        airports = find_airports_in_radius(lat, lon, radius, max_results=5)
        if airports:
            return airports[0]
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  GROUND TRANSPORT
# ─────────────────────────────────────────────────────────────────────────────

# INR per km  (conservative estimates)
_RATES  = {"walk": 0,  "metro": 3.0,  "cab": 16.0,  "bus": 4.0,  "train": 2.5}
_SPEEDS = {"walk": 5,  "metro": 35,   "cab": 55,    "bus": 50,   "train": 70}


def _pick_mode(dist_km: float) -> str:
    if dist_km <= 0.3:   return "walk"
    if dist_km <= 8:     return "metro"
    if dist_km <= 40:    return "cab"
    if dist_km <= 200:   return "bus"
    return "train"


def ground_transport(dist_km: float) -> dict:
    """Compute ground transport mode, cost, and time for a given distance."""
    mode  = _pick_mode(dist_km)
    cost  = round(dist_km * _RATES[mode])
    mins  = max(5, int((dist_km / _SPEEDS[mode]) * 60))
    notes = {
        "walk":  "Walking distance",
        "metro": f"{dist_km} km metro / auto-rickshaw",
        "cab":   f"{dist_km} km cab (Ola/Uber/Rapido)",
        "bus":   f"{dist_km} km state or private bus",
        "train": f"{dist_km} km train (sleeper class)",
    }
    emoji = {"walk": "🚶", "metro": "🚇", "cab": "🚖", "bus": "🚌", "train": "🚂"}
    return {
        "mode":     mode,
        "emoji":    emoji[mode],
        "cost_inr": cost,
        "time_min": mins,
        "note":     notes[mode],
    }
