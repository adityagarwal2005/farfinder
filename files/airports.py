"""
airports.py — Airport discovery, geocoding, ground transport, real last-mile data
"""
from __future__ import annotations
import csv, io, math, threading, time
import requests

# ─── Nominatim rate-limit ────────────────────────────────────────────
_last_nom = 0.0
_nom_lock = threading.Lock()

def _nom_get(params: dict) -> list:
    global _last_nom
    with _nom_lock:
        gap = 1.15 - (time.time() - _last_nom)
        if gap > 0:
            time.sleep(gap)
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={**params, "format": "json", "limit": 1},
                headers={"User-Agent": "FarFinder/3.1"},
                timeout=10,
            )
            r.raise_for_status()
            _last_nom = time.time()
            return r.json()
        except Exception as e:
            print(f"⚠️  Nominatim: {e}")
            return []

def geocode_location(query: str) -> tuple[float, float] | None:
    res = _nom_get({"q": query})
    if not res: return None
    return float(res[0]["lat"]), float(res[0]["lon"])

# ─── Haversine ──────────────────────────────────────────────────────
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ─── OpenFlights DB ─────────────────────────────────────────────────
_AIRPORTS_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights"
    "/master/data/airports.dat"
)
_ap_cache: list[dict] | None = None
_ap_lock = threading.Lock()

def load_airports() -> list[dict]:
    global _ap_cache
    with _ap_lock:
        if _ap_cache is not None:
            return _ap_cache
        try:
            r = requests.get(_AIRPORTS_URL, timeout=25)
            r.raise_for_status()
        except Exception as e:
            print(f"⚠️  Airport DB: {e}")
            _ap_cache = []
            return []
        airports: list[dict] = []
        for row in csv.reader(io.StringIO(r.text)):
            try:
                if len(row) < 9: continue
                iata = row[4].strip().strip('"')
                if not iata or iata == r"\N" or len(iata) != 3: continue
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
        _ap_cache = airports
        print(f"✅  {len(airports):,} airports loaded")
        return _ap_cache

def find_airports_in_radius(lat: float, lon: float, radius_km: float, max_results: int = 15) -> list[dict]:
    nearby = []
    for ap in load_airports():
        d = haversine(lat, lon, ap["lat"], ap["lon"])
        if d <= radius_km:
            nearby.append({**ap, "distance_km": round(d, 1)})
    nearby.sort(key=lambda x: x["distance_km"])
    return nearby[:max_results]

def resolve_destination_airport(dest: str) -> dict | None:
    coords = geocode_location(dest)
    if not coords: return None
    lat, lon = coords
    for r in (60, 150, 300, 600):
        hits = find_airports_in_radius(lat, lon, r, max_results=3)
        if hits: return hits[0]
    return None

# ─── IATA lookup ─────────────────────────────────────────────────────
CITY_IATA: dict[str, str] = {
    "delhi":"DEL","new delhi":"DEL","dilli":"DEL","ndls":"DEL",
    "mumbai":"BOM","bombay":"BOM",
    "bangalore":"BLR","bengaluru":"BLR",
    "hyderabad":"HYD","hyd":"HYD",
    "chennai":"MAA","madras":"MAA",
    "kolkata":"CCU","calcutta":"CCU",
    "ahmedabad":"AMD","amd":"AMD",
    "pune":"PNQ",
    "kochi":"COK","cochin":"COK","goa":"GOI",
    "jaipur":"JAI","lucknow":"LKO","varanasi":"VNS","banaras":"VNS",
    "agra":"AGR","bhopal":"BHO","indore":"IDR","nagpur":"NAG",
    "chandigarh":"IXC","amritsar":"ATQ","srinagar":"SXR","jammu":"IXJ",
    "leh":"IXL","dehradun":"DED","patna":"PAT","ranchi":"IXR",
    "bhubaneswar":"BBI","raipur":"RPR","visakhapatnam":"VTZ","vizag":"VTZ",
    "coimbatore":"CJB","madurai":"IXM","tiruchirappalli":"TRZ","trichy":"TRZ",
    "thiruvananthapuram":"TRV","trivandrum":"TRV","kozhikode":"CCJ","calicut":"CCJ",
    "mangalore":"IXE","hubli":"HBX","belgaum":"IXG","belagavi":"IXG",
    "port blair":"IXZ","guwahati":"GAU","dibrugarh":"DIB","imphal":"IMF",
    "bagdogra":"IXB","siliguri":"IXB","udaipur":"UDR","jodhpur":"JDH",
    "aurangabad":"IXU","shirdi":"SAG","surat":"STV",
    "vadodara":"BDQ","baroda":"BDQ","rajkot":"RAJ","bhavnagar":"BHU",
    "jabalpur":"JLR","gorakhpur":"GOP","prayagraj":"IXD","allahabad":"IXD",
    "gwalior":"GWL","tirupati":"TIR","vijayawada":"VGA","kannur":"CNN",
    "mysore":"MYQ","mysuru":"MYQ","shimla":"SLV","dharamshala":"DHM",
    "dubai":"DXB","abu dhabi":"AUH","doha":"DOH","singapore":"SIN",
    "bangkok":"BKK","kuala lumpur":"KUL","london":"LHR",
    "new york":"JFK","toronto":"YYZ","sydney":"SYD",
}

def city_to_iata(city: str) -> str | None:
    """Return IATA code for city name. Tries exact match, partial, then treats as IATA."""
    key = city.strip().lower()
    if not key: return None
    # Direct match
    if key in CITY_IATA: return CITY_IATA[key]
    # Partial match
    for k, v in CITY_IATA.items():
        if k in key or key in k: return v
    # Already an IATA code
    if len(key) == 3 and key.isalpha(): return key.upper()
    return None

def resolve_iata_robust(city_or_iata: str, search_radius_km: float = 80) -> str | None:
    """
    Most robust IATA resolution:
    1. Check hardcoded CITY_IATA table
    2. If looks like IATA code already, return it
    3. Geocode + find nearest airport
    """
    if not city_or_iata or not city_or_iata.strip():
        return None

    # Step 1: CITY_IATA table
    iata = city_to_iata(city_or_iata)
    if iata:
        return iata

    # Step 2: Geocode
    coords = geocode_location(city_or_iata)
    if not coords:
        return None
    lat, lon = coords
    for radius in (search_radius_km, search_radius_km * 2, 300):
        nearby = find_airports_in_radius(lat, lon, radius, max_results=3)
        if nearby:
            return nearby[0]["iata"]
    return None

# ─── Real per-airport last-mile data ────────────────────────────────
AIRPORT_LAST_MILE: dict[str, dict] = {
    "DEL": {"km": 19, "modes": [
        {"mode":"metro","label":"Delhi Metro Airport Express","cost":60,"mins":20,"emoji":"🚇"},
        {"mode":"cab","label":"Cab / Ola / Uber","cost":280,"mins":35,"emoji":"🚖"},
        {"mode":"bus","label":"DIMTS Airport Bus","cost":70,"mins":55,"emoji":"🚌"},
    ]},
    "BOM": {"km": 30, "modes": [
        {"mode":"cab","label":"Cab / Ola / Uber","cost":450,"mins":50,"emoji":"🚖"},
        {"mode":"train","label":"Local Train (Andheri)","cost":10,"mins":60,"emoji":"🚂"},
        {"mode":"bus","label":"BEST Bus","cost":30,"mins":75,"emoji":"🚌"},
    ]},
    "BLR": {"km": 40, "modes": [
        {"mode":"cab","label":"Cab / Ola / Uber","cost":600,"mins":55,"emoji":"🚖"},
        {"mode":"metro","label":"Namma Metro","cost":60,"mins":50,"emoji":"🚇"},
        {"mode":"bus","label":"BMTC Vayu Vajra","cost":190,"mins":90,"emoji":"🚌"},
    ]},
    "HYD": {"km": 25, "modes": [
        {"mode":"cab","label":"Cab / Ola / Uber","cost":350,"mins":40,"emoji":"🚖"},
        {"mode":"bus","label":"TSRTC Airport Bus","cost":150,"mins":65,"emoji":"🚌"},
    ]},
    "MAA": {"km": 20, "modes": [
        {"mode":"cab","label":"Cab / Ola / Uber","cost":280,"mins":35,"emoji":"🚖"},
        {"mode":"metro","label":"Chennai Metro","cost":50,"mins":40,"emoji":"🚇"},
        {"mode":"bus","label":"MTC Airport Bus","cost":50,"mins":60,"emoji":"🚌"},
    ]},
    "CCU": {"km": 17, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":240,"mins":40,"emoji":"🚖"},
        {"mode":"metro","label":"Kolkata Metro","cost":25,"mins":35,"emoji":"🚇"},
    ]},
    "PNQ": {"km": 15, "modes": [
        {"mode":"cab","label":"Cab / Ola / Uber","cost":225,"mins":30,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":150,"mins":40,"emoji":"🛺"},
    ]},
    "COK": {"km": 25, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":350,"mins":35,"emoji":"🚖"},
        {"mode":"bus","label":"KSRTC Airport Bus","cost":80,"mins":55,"emoji":"🚌"},
    ]},
    "GOI": {"km": 28, "modes": [
        {"mode":"cab","label":"Cab / Goa Taxi","cost":450,"mins":40,"emoji":"🚖"},
        {"mode":"bus","label":"KTC Bus","cost":50,"mins":75,"emoji":"🚌"},
    ]},
    "JAI": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":168,"mins":25,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":120,"mins":30,"emoji":"🛺"},
        {"mode":"bus","label":"RSRTC Bus","cost":30,"mins":45,"emoji":"🚌"},
    ]},
    "AMD": {"km": 14, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":196,"mins":25,"emoji":"🚖"},
        {"mode":"metro","label":"Ahmedabad Metro","cost":25,"mins":30,"emoji":"🚇"},
    ]},
    "IXC": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":168,"mins":20,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":100,"mins":25,"emoji":"🛺"},
    ]},
    "ATQ": {"km": 15, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":225,"mins":25,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":120,"mins":30,"emoji":"🛺"},
    ]},
    "LKO": {"km": 16, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":224,"mins":28,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":140,"mins":35,"emoji":"🛺"},
    ]},
    "VNS": {"km": 24, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":360,"mins":45,"emoji":"🚖"},
        {"mode":"bus","label":"UPSRTC Bus","cost":40,"mins":60,"emoji":"🚌"},
    ]},
    "VTZ": {"km": 16, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":224,"mins":28,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":140,"mins":35,"emoji":"🛺"},
    ]},
    "CJB": {"km": 14, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":196,"mins":25,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":120,"mins":30,"emoji":"🛺"},
    ]},
    "IXM": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":168,"mins":22,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":100,"mins":28,"emoji":"🛺"},
    ]},
    "TRZ": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":168,"mins":22,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":100,"mins":28,"emoji":"🛺"},
    ]},
    "TRV": {"km": 8, "modes": [
        {"mode":"auto","label":"Auto-rickshaw","cost":80,"mins":15,"emoji":"🛺"},
        {"mode":"cab","label":"Cab / Ola","cost":112,"mins":18,"emoji":"🚖"},
    ]},
    "CCJ": {"km": 22, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":330,"mins":35,"emoji":"🚖"},
        {"mode":"bus","label":"KSRTC Bus","cost":40,"mins":55,"emoji":"🚌"},
    ]},
    "IXE": {"km": 8, "modes": [
        {"mode":"auto","label":"Auto-rickshaw","cost":80,"mins":15,"emoji":"🛺"},
        {"mode":"cab","label":"Cab / Ola","cost":112,"mins":18,"emoji":"🚖"},
    ]},
    "GAU": {"km": 22, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":308,"mins":35,"emoji":"🚖"},
        {"mode":"bus","label":"ASTC Bus","cost":60,"mins":60,"emoji":"🚌"},
    ]},
    "UDR": {"km": 24, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":384,"mins":35,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":200,"mins":45,"emoji":"🛺"},
    ]},
    "JDH": {"km": 5, "modes": [
        {"mode":"auto","label":"Auto-rickshaw","cost":80,"mins":12,"emoji":"🛺"},
        {"mode":"cab","label":"Cab / Local Taxi","cost":80,"mins":10,"emoji":"🚖"},
    ]},
    "IDR": {"km": 8, "modes": [
        {"mode":"auto","label":"Auto-rickshaw","cost":80,"mins":15,"emoji":"🛺"},
        {"mode":"cab","label":"Cab / Ola","cost":112,"mins":18,"emoji":"🚖"},
    ]},
    "NAG": {"km": 8, "modes": [
        {"mode":"auto","label":"Auto-rickshaw","cost":80,"mins":15,"emoji":"🛺"},
        {"mode":"cab","label":"Cab / Ola","cost":112,"mins":18,"emoji":"🚖"},
    ]},
    "PAT": {"km": 5, "modes": [
        {"mode":"auto","label":"Auto-rickshaw","cost":70,"mins":12,"emoji":"🛺"},
        {"mode":"cab","label":"Cab / Ola","cost":70,"mins":10,"emoji":"🚖"},
    ]},
    "BBI": {"km": 4, "modes": [
        {"mode":"auto","label":"Auto-rickshaw","cost":56,"mins":10,"emoji":"🛺"},
        {"mode":"cab","label":"Cab","cost":56,"mins":8,"emoji":"🚖"},
    ]},
    "IXB": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":168,"mins":22,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":120,"mins":28,"emoji":"🛺"},
    ]},
    "IXR": {"km": 6, "modes": [
        {"mode":"auto","label":"Auto-rickshaw","cost":70,"mins":12,"emoji":"🛺"},
        {"mode":"cab","label":"Cab / Ola","cost":84,"mins":10,"emoji":"🚖"},
    ]},
    "GWL": {"km": 18, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":252,"mins":30,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":140,"mins":38,"emoji":"🛺"},
    ]},
    "IXU": {"km": 18, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":270,"mins":30,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":150,"mins":38,"emoji":"🛺"},
    ]},
    "STV": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":180,"mins":22,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":120,"mins":28,"emoji":"🛺"},
    ]},
    "BDQ": {"km": 18, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":252,"mins":30,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":140,"mins":38,"emoji":"🛺"},
    ]},
    "RAJ": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":180,"mins":22,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":120,"mins":28,"emoji":"🛺"},
    ]},
    "AGR": {"km": 14, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":210,"mins":25,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":140,"mins":32,"emoji":"🛺"},
    ]},
    "BHO": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":168,"mins":22,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":100,"mins":28,"emoji":"🛺"},
    ]},
    "RPR": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":168,"mins":22,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":100,"mins":28,"emoji":"🛺"},
    ]},
    "MYQ": {"km": 12, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":168,"mins":25,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":100,"mins":30,"emoji":"🛺"},
    ]},
    "TIR": {"km": 15, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":210,"mins":25,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":120,"mins":30,"emoji":"🛺"},
    ]},
    "VGA": {"km": 20, "modes": [
        {"mode":"cab","label":"Cab / Local Taxi","cost":280,"mins":30,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":150,"mins":38,"emoji":"🛺"},
    ]},
    "DED": {"km": 20, "modes": [
        {"mode":"cab","label":"Cab / Ola","cost":280,"mins":35,"emoji":"🚖"},
        {"mode":"bus","label":"Roadways Bus","cost":40,"mins":55,"emoji":"🚌"},
    ]},
    "SXR": {"km": 14, "modes": [
        {"mode":"cab","label":"Local Taxi / Cab","cost":280,"mins":25,"emoji":"🚖"},
        {"mode":"auto","label":"Auto-rickshaw","cost":200,"mins":30,"emoji":"🛺"},
    ]},
    "DXB": {"km": 15, "modes": [
        {"mode":"metro","label":"Dubai Metro (Red Line)","cost":110,"mins":25,"emoji":"🚇"},
        {"mode":"cab","label":"Careem / Uber","cost":270,"mins":20,"emoji":"🚖"},
    ]},
    "DOH": {"km": 20, "modes": [
        {"mode":"metro","label":"Doha Metro","cost":80,"mins":30,"emoji":"🚇"},
        {"mode":"cab","label":"Karwa Taxi","cost":360,"mins":25,"emoji":"🚖"},
    ]},
    "SIN": {"km": 20, "modes": [
        {"mode":"metro","label":"MRT East-West Line","cost":130,"mins":28,"emoji":"🚇"},
        {"mode":"cab","label":"Grab / Taxi","cost":400,"mins":25,"emoji":"🚖"},
    ]},
}

def last_mile_info(dest_iata: str) -> dict:
    iata = dest_iata.upper()
    if iata in AIRPORT_LAST_MILE:
        data  = AIRPORT_LAST_MILE[iata]
        modes = data["modes"]
    else:
        km   = 15
        cost = km * 15
        mins = max(20, int((km / 35) * 60))
        modes = [{"mode":"cab","label":"Cab / Ola / Uber","cost":cost,"mins":mins,"emoji":"🚖"}]

    cheapest = min(modes, key=lambda m: m["cost"])
    return {
        "km":            AIRPORT_LAST_MILE.get(iata, {}).get("km", 15),
        "modes":         modes,
        "cheapest_mode": cheapest,
        "cheapest_cost": cheapest["cost"],
        "cheapest_mins": cheapest["mins"],
    }

def last_mile_cost(dest_iata: str) -> dict:
    info = last_mile_info(dest_iata)
    return {
        "km":   info["km"],
        "cost": info["cheapest_cost"],
        "mins": info["cheapest_mins"],
        "note": f"{info['cheapest_mode']['label']} from airport",
    }

# ─── Origin ground transport ─────────────────────────────────────────
_RATE  = {"walk":0,"metro":3.5,"cab":16.0,"bus":4.5,"train":2.8}
_SPEED = {"walk":5,"metro":32,"cab":55,"bus":50,"train":75}
_EMOJI = {"walk":"🚶","metro":"🚇","cab":"🚖","bus":"🚌","train":"🚂"}
_NOTE  = {
    "walk": "Walking distance",
    "metro":"Metro / auto-rickshaw",
    "cab":  "Cab (Ola / Uber / Rapido)",
    "bus":  "State bus / private bus",
    "train":"Train (sleeper class)",
}

def _pick_mode(dist_km: float) -> str:
    if dist_km <= 0.4:  return "walk"
    if dist_km <= 10:   return "metro"
    if dist_km <= 45:   return "cab"
    if dist_km <= 220:  return "bus"
    return "train"

def ground_transport(dist_km: float) -> dict:
    mode = _pick_mode(dist_km)
    cost = round(dist_km * _RATE[mode])
    mins = max(5, int((dist_km / _SPEED[mode]) * 60))
    return {
        "mode":     mode,
        "emoji":    _EMOJI[mode],
        "cost_inr": cost,
        "time_min": mins,
        "note":     f"{_NOTE[mode]} · {dist_km} km",
    }

# ─── Intercity ground-only routes ────────────────────────────────────
_IC_RATE  = {"cab":12.0,"bus":1.5,"train":0.8}
_IC_SPEED = {"cab":65,"bus":55,"train":70}
_IC_EMOJI = {"cab":"🚖","bus":"🚌","train":"🚂"}

def intercity_ground_routes(
    origin_city: str, dest_city: str,
    origin_coords: tuple[float, float], dest_coords: tuple[float, float],
) -> list[dict]:
    dist = haversine(*origin_coords, *dest_coords)
    if dist < 10: return []
    routes = []
    modes = []
    if dist <= 400: modes.append("cab")
    if dist <= 1800: modes.append("bus")
    modes.append("train")
    for mode in modes:
        cost  = round(dist * _IC_RATE[mode])
        speed = _IC_SPEED[mode]
        mins  = int((dist / speed) * 60)
        routes.append({
            "route_type": "ground_only",
            "origin_city": origin_city,
            "origin_airport": {"iata":"—","name":f"{origin_city} city","city":origin_city,"distance_km":0.0},
            "destination": {"iata":"—","city":dest_city,"name":dest_city},
            "ground": {"mode":mode,"emoji":_IC_EMOJI[mode],"cost_inr":cost,"time_min":mins,"note":f"~{round(dist)} km intercity {mode}"},
            "flight": None,
            "total_cost_inr": cost,
            "total_time_min": mins,
            "savings_inr": 0,
            "confidence": "medium",
            "fallback_used": False,
            "booking_links": {},
            "last_mile": {"cost":0,"mins":0,"km":0,"note":"Door-to-door"},
            "last_mile_modes": [],
            "journey_breakdown": [
                {"step":f"Intercity {mode}","desc":f"{origin_city} → {dest_city}","mode":mode,"emoji":_IC_EMOJI[mode],"cost":cost,"time":mins},
            ],
        })
    return routes