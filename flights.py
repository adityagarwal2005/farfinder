"""
flights.py — Travelpayouts Data API wrapper
"""
from __future__ import annotations
import os
from datetime import date, datetime, timedelta
import requests

TOKEN    = os.getenv("TRAVELPAYOUTS_TOKEN", "9f5646b1e8ffe0f51ba473251ab857c6")
BASE     = "https://api.travelpayouts.com"
HEADERS  = {"x-access-token": TOKEN, "Accept-Encoding": "gzip,deflate"}
CURRENCY = "inr"

AIRLINES: dict[str, str] = {
    "6E":"IndiGo","SG":"SpiceJet","AI":"Air India","UK":"Vistara",
    "IX":"AirAsia India","QP":"Akasa Air","G8":"GoFirst","I5":"AirAsia",
    "S5":"Star Air","EK":"Emirates","QR":"Qatar Airways","EY":"Etihad",
    "SQ":"Singapore Air","BA":"British Airways","LH":"Lufthansa",
    "FZ":"flydubai","WY":"Oman Air","TK":"Turkish Airlines",
    "AF":"Air France","KL":"KLM","MH":"Malaysia Airlines",
    "TG":"Thai Airways","CX":"Cathay Pacific","UL":"SriLankan",
}

INDIA_HUBS = ["DEL","BOM","BLR","HYD","MAA","CCU","AMD"]

def airline_name(code: str) -> str:
    if not code: return "Unknown"
    return AIRLINES.get(code.strip().upper(), code.upper())

def fmt_dur(minutes: int | None) -> str:
    if not minutes: return "—"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"

def _safe_date(s: str | None) -> date | None:
    if not s: return None
    try: return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except: return None

def _get(path: str, params: dict) -> dict | None:
    try:
        r = requests.get(
            f"{BASE}{path}", headers=HEADERS,
            params={**params, "token": TOKEN}, timeout=18,
        )
        if r.status_code in (400, 404, 422, 429): return None
        r.raise_for_status()
        data = r.json()
        if not data.get("success", True): return None
        return data
    except requests.Timeout:
        print(f"⚠️  Timeout: {path}"); return None
    except Exception as e:
        print(f"⚠️  API [{path}]: {e}"); return None

def search_cheap(origin: str, dest: str, month: str) -> list[dict]:
    data = _get("/v1/prices/cheap", {
        "origin":origin.upper(),"destination":dest.upper(),
        "depart_date":month,"currency":CURRENCY,
    })
    if not data: return []
    results = []
    for stop_key, info in data.get("data",{}).get(dest.upper(),{}).items():
        price = info.get("price",0)
        if price <= 0: continue
        carrier = info.get("airline","")
        dep_raw = info.get("departure_at","")
        results.append({
            "price_inr":price,"carrier":airline_name(carrier),
            "carrier_code":carrier,"stops":int(stop_key),
            "dep_date":dep_raw[:10] if dep_raw else "",
            "departure_at":dep_raw,"duration_min":None,
            "duration_fmt":"—","source":"cheap",
        })
    results.sort(key=lambda x: x["price_inr"])
    return results

def search_direct(origin: str, dest: str, month: str) -> list[dict]:
    data = _get("/v1/prices/direct", {
        "origin":origin.upper(),"destination":dest.upper(),
        "depart_date":month,"currency":CURRENCY,
    })
    if not data: return []
    results = []
    for _, info in data.get("data",{}).get(dest.upper(),{}).items():
        price = info.get("price",0)
        if price <= 0: continue
        carrier = info.get("airline","")
        dep_raw = info.get("departure_at","")
        results.append({
            "price_inr":price,"carrier":airline_name(carrier),
            "carrier_code":carrier,"stops":0,
            "dep_date":dep_raw[:10] if dep_raw else "",
            "departure_at":dep_raw,"duration_min":None,
            "duration_fmt":"—","source":"direct",
        })
    results.sort(key=lambda x: x["price_inr"])
    return results

def get_latest_prices(origin: str, dest: str, limit: int = 20) -> list[dict]:
    data = _get("/aviasales/v3/get_latest_prices", {
        "origin":origin.upper(),"destination":dest.upper(),
        "currency":CURRENCY,"period_type":"day",
        "show_to_affiliates":"true","sorting":"price",
        "one_way":"true","limit":limit,
    })
    if not data or not data.get("data"): return []
    results = []
    for item in data["data"]:
        price = item.get("value",0)
        if price <= 0: continue
        carrier = item.get("airline","")
        dur = item.get("duration",None)
        results.append({
            "price_inr":price,"carrier":airline_name(carrier),
            "carrier_code":carrier,"stops":item.get("number_of_changes",0),
            "dep_date":item.get("depart_date",""),
            "departure_at":item.get("departure_at",""),
            "duration_min":dur,"duration_fmt":fmt_dur(dur),"source":"latest",
        })
    results.sort(key=lambda x: x["price_inr"])
    return results

def search_best(origin: str, dest: str, depart_date: str, max_results: int = 20) -> list[dict]:
    month = depart_date[:7]
    merged: list[dict] = []
    merged.extend(search_cheap(origin, dest, month))
    merged.extend(search_direct(origin, dest, month))
    merged.extend(get_latest_prices(origin, dest, limit=20))
    if not merged:
        try:
            dt   = datetime.strptime(depart_date, "%Y-%m-%d")
            prev = (dt.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            nxt  = (dt.replace(day=28) + timedelta(days=4)).strftime("%Y-%m")
            for alt in [prev, nxt]:
                merged.extend(search_cheap(origin, dest, alt))
                merged.extend(search_direct(origin, dest, alt))
            if not merged:
                merged.extend(get_latest_prices(origin, dest, limit=30))
        except Exception:
            pass
    if not merged: return []
    seen: set[tuple] = set()
    unique: list[dict] = []
    for r in merged:
        key = (r.get("carrier_code",""),int(r.get("stops",0) or 0),
               r.get("dep_date",""),int(r.get("price_inr",0) or 0))
        if key not in seen:
            seen.add(key); unique.append(r)
    target = _safe_date(depart_date)
    def _score(row: dict) -> tuple:
        dep = _safe_date(row.get("dep_date",""))
        gap = abs((dep - target).days) if dep and target else 999
        return (int(row.get("price_inr",10**9)),gap,
                int(row.get("stops",9) or 9),
                int(row.get("duration_min",10**6) or 10**6))
    unique.sort(key=_score)
    return unique[:max_results]

def search_connecting_via_hubs(origin: str, dest: str, depart_date: str, hubs: list[str] | None = None) -> list[dict]:
    if hubs is None: hubs = INDIA_HUBS
    results: list[dict] = []
    for hub in hubs:
        if hub in (origin.upper(), dest.upper()): continue
        leg1_list = search_best(origin, hub, depart_date, max_results=5)
        leg2_list = search_best(hub, dest, depart_date, max_results=5)
        if not leg1_list or not leg2_list: continue
        leg1, leg2 = leg1_list[0], leg2_list[0]
        combined_price = leg1["price_inr"] + leg2["price_inr"]
        combined_dur   = (leg1.get("duration_min") or 90) + (leg2.get("duration_min") or 90) + 90
        results.append({
            "price_inr":combined_price,
            "carrier":f"{leg1['carrier']} + {leg2['carrier']}",
            "carrier_code":leg1["carrier_code"],
            "stops":1,"dep_date":leg1.get("dep_date",depart_date),
            "departure_at":leg1.get("departure_at",""),
            "duration_min":combined_dur,"duration_fmt":fmt_dur(combined_dur),
            "source":"connecting","connecting_via":hub,
            "legs":[
                {"from":origin.upper(),"to":hub,"flight":leg1},
                {"from":hub,"to":dest.upper(),"flight":leg2},
            ],
        })
    results.sort(key=lambda x: x["price_inr"])
    return results

def get_price_calendar(origin: str, dest: str, month: str) -> dict[str, dict]:
    data = _get("/v1/prices/calendar", {
        "origin":origin.upper(),"destination":dest.upper(),
        "month":month,"calendar_type":"departure_date","currency":CURRENCY,
    })
    if not data or not data.get("data"): return {}
    cal: dict[str, dict] = {}
    for key, info in data["data"].items():
        if not isinstance(info, dict): continue
        price = info.get("price",0)
        if price <= 0: continue
        carrier = info.get("airline","")
        cal[key[:10]] = {
            "price":price,"airline":airline_name(carrier),
            "airline_code":carrier,"stops":info.get("transfers",0),
        }
    return cal

def search_flexible(origin: str, dest: str, target_date_str: str, flex_days: int = 3) -> list[dict]:
    td = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    months: set[str] = set()
    for off in range(-flex_days, flex_days + 1):
        months.add((td + timedelta(days=off)).strftime("%Y-%m"))
    cal: dict[str, dict] = {}
    for m in months:
        cal.update(get_price_calendar(origin, dest, m))
    results = []
    today = date.today()
    for off in range(-flex_days, flex_days + 1):
        check = td + timedelta(days=off)
        if check < today: continue
        dstr = check.strftime("%Y-%m-%d")
        entry = cal.get(dstr)
        if entry:
            results.append({
                "date":dstr,"days_diff":off,"is_target":off==0,
                "label":"Target" if off==0 else (f"+{off}d" if off>0 else f"{off}d"),
                "price":entry["price"],"airline":entry["airline"],"stops":entry["stops"],
            })
    results.sort(key=lambda x: x["price"])
    return results

def get_monthly_cheapest(origin: str, dest: str) -> list[dict]:
    data = _get("/v1/prices/monthly", {
        "origin":origin.upper(),"destination":dest.upper(),"currency":CURRENCY,
    })
    if not data or not data.get("data"): return []
    results = []
    for month_str, info in data["data"].items():
        if not isinstance(info, dict): continue
        price = info.get("price",0)
        if price <= 0: continue
        results.append({
            "month":month_str,"price":price,
            "airline":airline_name(info.get("airline","")),"stops":info.get("transfers",0),
        })
    results.sort(key=lambda x: x["month"])
    return results[:9]

def search_by_budget(origin: str, budget_max: int = 5000, budget_min: int = 0,
                     currency: str = "inr", direct_only: bool = False, limit: int = 50) -> list[dict]:
    data = _get("/aviasales/v3/search_by_price_range", {
        "origin":origin.upper(),"destination":"-",
        "value_min":budget_min,"value_max":budget_max,
        "one_way":"true","direct":"true" if direct_only else "false",
        "currency":currency,"locale":"en","market":"in",
        "show_to_affiliates":"true","limit":limit,"page":1,
    })
    if not data or not data.get("data"): return []
    results = []
    for item in data["data"]:
        price = item.get("value",0)
        if price <= 0: continue
        carrier = item.get("airline","")
        dur = item.get("duration",None)
        results.append({
            "destination":item.get("destination_name",""),
            "destination_iata":item.get("destination_code",""),
            "price":price,"airline":airline_name(carrier),"airline_code":carrier,
            "stops":item.get("number_of_changes",0),
            "dep_date":item.get("departure_at","")[:10],
            "duration_min":dur,"duration_fmt":fmt_dur(dur),
        })
    results.sort(key=lambda x: x["price"])
    return results

def classify_price_trend(origin: str, dest: str, current_price: int) -> dict:
    monthly = get_monthly_cheapest(origin, dest)
    if not monthly: return {"trend":"unknown","label":"No trend data","pct":0}
    prices = [m["price"] for m in monthly]
    avg = sum(prices)/len(prices) if prices else 0
    if avg == 0: return {"trend":"unknown","label":"No trend data","pct":0}
    pct = round((current_price - avg)/avg*100, 1)
    if pct <= -15: return {"trend":"cheap","label":f"🟢 {abs(pct):.0f}% below avg — great time to book","pct":pct}
    elif pct >= 20: return {"trend":"expensive","label":f"🔴 {pct:.0f}% above avg","pct":pct}
    else:           return {"trend":"normal","label":"🟡 Near average price","pct":pct}

def booking_links(origin: str, dest: str, dep_date: str, adults: int = 1) -> dict[str, str]:
    o, d = origin.upper(), dest.upper()
    try:
        dt = datetime.strptime(dep_date, "%Y-%m-%d")
        mmt = dt.strftime("%d/%m/%Y")
        sky = dep_date.replace("-","")
    except:
        mmt = dep_date; sky = dep_date
    return {
        "Skyscanner": f"https://www.skyscanner.co.in/transport/flights/{o.lower()}/{d.lower()}/{sky}/?adults={adults}&currency=INR",
        "MakeMyTrip": f"https://www.makemytrip.com/flight/search?itinerary={o}-{d}-{mmt}&tripType=O&paxType=A-{adults}_C-0_I-0&intl=false&cabinClass=E&lang=eng",
        "Goibibo":    f"https://www.goibibo.com/flights/search/?src={o}&dst={d}&date={sky}&adults={adults}&children=0&infants=0&class=e&seType=SR",
        "Cleartrip":  f"https://www.cleartrip.com/flights/results?from={o}&to={d}&depart_date={dep_date}&adults={adults}&childs=0&infants=0&class=Economy",
    }