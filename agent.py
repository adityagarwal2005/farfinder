"""
agent.py — FarFinder v3 FastAPI backend
Run: uvicorn agent:app --reload --port 8001
"""
from __future__ import annotations
import json, os, re
from datetime import date, datetime, timedelta

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from airports import (
    geocode_location, find_airports_in_radius,
    resolve_destination_airport, city_to_iata,
    resolve_iata_robust, intercity_ground_routes,
    last_mile_info,
)
from flights import (
    get_price_calendar, search_flexible, search_by_budget,
    get_monthly_cheapest, classify_price_trend,
)
from routes import build_routes, generate_insights, build_comparison_table

app = FastAPI(title="FarFinder v3", version="3.2.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ── Models ────────────────────────────────────────────────────────────
class SearchReq(BaseModel):
    origin:      str
    destination: str
    date:        str
    radius_km:   float = Field(default=100.0, ge=2, le=1200)
    adults:      int   = Field(default=1, ge=1, le=9)
    direct_only: bool  = False

class NLReq(BaseModel):
    query: str

class CalendarReq(BaseModel):
    origin:      str
    destination: str
    month:       str   # YYYY-MM

class FlexibleReq(BaseModel):
    origin:      str
    destination: str
    date:        str   # YYYY-MM-DD
    flex_days:   int = Field(default=3, ge=1, le=14)

class BudgetReq(BaseModel):
    origin:      str
    budget_max:  int  = Field(default=5000, ge=100)
    budget_min:  int  = 0
    direct_only: bool = False

class TrendReq(BaseModel):
    origin:      str
    destination: str

class CompareReq(BaseModel):
    origin:      str
    destination: str
    date:        str
    radius_km:   float = 150.0

class WeatherReq(BaseModel):
    city: str

class LastMileReq(BaseModel):
    iata: str

# ── NL Parser ─────────────────────────────────────────────────────────
_NL_PROMPT = """Today: {today}. Parse this query and return ONLY valid JSON (no markdown):
{{"origin":"city or 'unknown'","destination":"city or 'unknown'","date":"YYYY-MM-DD","radius_km":100,"adults":1,"direct_only":false,"flex_days":0,"confidence":"high|medium|low"}}
Aliases: Bombay=Mumbai,Calcutta=Kolkata,Madras=Chennai,Dilli=Delhi,Bengaluru=Bangalore.
Radius: "nearby"=80,"200km"=200,absent=100. "non-stop"/"direct"→direct_only=true. Date absent→7 days from today.
Hinglish: "Dilli se Mumbai 200km" → origin=Delhi,destination=Mumbai,radius=200.
QUERY: "{query}"
"""

def _parse_nl_llm(query: str) -> dict:
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},
        json={"model":"deepseek/deepseek-chat","temperature":0.05,"max_tokens":220,
              "response_format":{"type":"json_object"},
              "messages":[{"role":"user","content":_NL_PROMPT.format(today=date.today().isoformat(),query=query)}]},
        timeout=18,
    )
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])

def _parse_nl_regex(q: str) -> dict:
    ql = q.lower()
    radius = 100.0
    if m := re.search(r"(\d+)\s*km", ql): radius = float(m.group(1))
    elif "nearby" in ql: radius = 80.0
    travel_date = (date.today() + timedelta(days=7)).isoformat()
    if "tomorrow" in ql: travel_date = (date.today() + timedelta(days=1)).isoformat()
    elif "next week" in ql: travel_date = (date.today() + timedelta(days=7)).isoformat()
    elif m := re.search(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?", ql):
        try:
            d, mo = int(m.group(1)), int(m.group(2))
            yr = int(m.group(3)) if m.group(3) else date.today().year
            yr = yr if yr > 99 else 2000 + yr
            travel_date = date(yr, mo, d).isoformat()
        except: pass
    origin, destination = "unknown", "unknown"
    if " to " in ql:
        a, b = ql.split(" to ", 1)
        destination = b.strip().split()[0].title()
        for kw in ["from","fly","travel","going"]:
            if kw in a:
                origin = a.split(kw)[-1].strip().split()[0].title(); break
        if origin == "unknown" and a.strip():
            origin = a.strip().split()[-1].title()
    elif " se " in ql:
        a, b = ql.split(" se ", 1)
        origin = a.strip().split()[-1].title()
        destination = b.strip().split()[0].title()
    return {"origin":origin,"destination":destination,"date":travel_date,"radius_km":radius,
            "adults":1,"direct_only":any(x in ql for x in ["non-stop","nonstop","direct only"]),
            "flex_days":3 if "flex" in ql else 0,"confidence":"low"}

def parse_nl(query: str) -> dict:
    if OPENROUTER_KEY:
        try: return _parse_nl_llm(query)
        except Exception as e: print(f"⚠️  LLM parse: {e}")
    return _parse_nl_regex(query)

# ── Core search ────────────────────────────────────────────────────────
def _run_search(
    origin: str, destination: str,
    travel_date: str, radius_km: float,
    adults: int = 1, direct_only: bool = False,
) -> dict:
    try:
        td = datetime.strptime(travel_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")
    if td < date.today():
        raise HTTPException(400, "Travel date is in the past.")

    origin_coords = geocode_location(origin)
    if not origin_coords:
        raise HTTPException(400, f"Cannot geocode origin: '{origin}'")
    olat, olon = origin_coords

    dest_ap = resolve_destination_airport(destination)
    if not dest_ap:
        raise HTTPException(400, f"Cannot find airport near '{destination}'.")

    dest_coords = geocode_location(destination)

    radii = sorted({float(radius_km), float(radius_km)*1.5, float(radius_km)*2.5, float(radius_km)*4.0})
    radii = [min(1200.0, round(v,1)) for v in radii]

    aggregate: list[dict] = []
    airports_checked: set[str] = set()
    final_radius = radius_km
    strategy = "direct"

    for lvl in radii:
        nearby = find_airports_in_radius(olat, olon, lvl)
        if not nearby: continue
        nearby_f = [ap for ap in nearby if ap["iata"] != dest_ap["iata"]]
        if not nearby_f: nearby_f = nearby
        for ap in nearby_f:
            airports_checked.add(ap["iata"])

        chunk = build_routes(
            nearby_airports=nearby_f, dest_airport=dest_ap,
            departure_date=travel_date, origin_city=origin.title(),
            adults=adults, max_flights_per_airport=10,
        )
        if direct_only:
            chunk = [r for r in chunk if r.get("flight") and r["flight"]["stops"] == 0]

        seen = {
            (r["origin_airport"]["iata"],
             r.get("flight",{}).get("carrier_code",""),
             int(r.get("total_cost_inr",0)))
            for r in aggregate
        }
        for r in chunk:
            k = (r["origin_airport"]["iata"],
                 r.get("flight",{}).get("carrier_code",""),
                 int(r.get("total_cost_inr",0)))
            if k not in seen:
                seen.add(k); aggregate.append(r)

        if aggregate:
            final_radius = lvl
            if lvl > radius_km: strategy = "expanded"
        if len(aggregate) >= 30: break

    if dest_coords:
        ground_routes = intercity_ground_routes(
            origin.title(), destination.title(), origin_coords, dest_coords,
        )
        aggregate.extend(ground_routes)

    if not aggregate:
        raise HTTPException(404,
            "No routes found. Try popular routes: Delhi↔Mumbai, Bangalore↔Hyderabad. "
            "Travelpayouts returns cached prices from real user searches.")

    aggregate.sort(key=lambda r: (r["total_cost_inr"], r["total_time_min"]))

    home_routes = [r for r in aggregate if r.get("route_type") == "direct"]
    ref = home_routes[0]["total_cost_inr"] if home_routes else aggregate[0]["total_cost_inr"]
    for r in aggregate:
        r["savings_inr"] = max(0, ref - r["total_cost_inr"])

    insights   = generate_insights(aggregate)
    comparison = build_comparison_table(aggregate)

    origin_iata = aggregate[0]["origin_airport"]["iata"] if aggregate else ""
    monthly = []
    if origin_iata and origin_iata != "—":
        try: monthly = get_monthly_cheapest(origin_iata, dest_ap["iata"])
        except: pass

    system_msgs: list[str] = []
    if strategy == "expanded":
        system_msgs.append(f"Search expanded to {int(final_radius)} km for better coverage.")
    system_msgs.append(f"{len(aggregate)} options across {len(airports_checked)} airports.")

    return {
        "search": {
            "origin":origin.title(),"destination":destination.title(),
            "date":travel_date,"radius_km":radius_km,
            "final_radius":final_radius,"adults":adults,
        },
        "system_message": system_msgs,
        "airports_checked": len(airports_checked),
        "destination_airport": dest_ap,
        "total_routes": len(aggregate),
        "routes": aggregate[:40],
        "comparison_table": comparison,
        "insights": insights,
        "monthly_cheapest": monthly,
    }

# ── Endpoints ──────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status":"ok","version":"3.2.0","api":"Travelpayouts Data API"}

@app.post("/parse-query")
def endpoint_parse(req: NLReq):
    return {"query":req.query,"parsed":parse_nl(req.query)}

@app.post("/search")
def endpoint_search(req: SearchReq):
    return _run_search(req.origin,req.destination,req.date,req.radius_km,req.adults,req.direct_only)

@app.post("/search-nl")
def endpoint_search_nl(req: NLReq):
    parsed = parse_nl(req.query)
    if parsed.get("origin","unknown").lower() == "unknown":
        raise HTTPException(400,"Could not detect origin city.")
    if parsed.get("destination","unknown").lower() == "unknown":
        raise HTTPException(400,"Could not detect destination city.")
    result = _run_search(
        origin=parsed["origin"],destination=parsed["destination"],
        travel_date=parsed.get("date") or (date.today()+timedelta(days=7)).isoformat(),
        radius_km=float(parsed.get("radius_km",100)),
        adults=int(parsed.get("adults",1)),
        direct_only=bool(parsed.get("direct_only",False)),
    )
    result["parsed_query"] = parsed
    return result

@app.post("/calendar")
def endpoint_calendar(req: CalendarReq):
    """
    Resolve both city names to IATA codes robustly, then fetch price calendar.
    """
    o = resolve_iata_robust(req.origin)
    if not o:
        raise HTTPException(400, f"Cannot resolve origin airport for '{req.origin}'. "
                                 f"Try using IATA code (e.g. JAI for Jaipur).")

    d = resolve_iata_robust(req.destination)
    if not d:
        raise HTTPException(400, f"Cannot resolve destination airport for '{req.destination}'. "
                                 f"Try using IATA code (e.g. BOM for Mumbai).")

    # Validate month format
    try:
        datetime.strptime(req.month + "-01", "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid month format. Use YYYY-MM (e.g. 2025-06).")

    cal = get_price_calendar(o, d, req.month)
    if not cal:
        return {
            "origin": o, "destination": d, "month": req.month,
            "calendar": {}, "cheapest_day": None, "days_with_data": 0,
            "message": (
                f"No cached price data for {o}→{d} in {req.month}. "
                "Travelpayouts only has data for recently searched routes. "
                "Try DEL↔BOM, BLR↔HYD, or MAA↔DEL."
            ),
        }

    cheapest = min(cal.items(), key=lambda x: x[1]["price"])
    return {
        "origin": o, "destination": d, "month": req.month,
        "calendar": cal,
        "cheapest_day": {
            "date":    cheapest[0],
            "price":   cheapest[1]["price"],
            "airline": cheapest[1]["airline"],
        },
        "days_with_data": len(cal),
    }

@app.post("/flexible")
def endpoint_flexible(req: FlexibleReq):
    """
    Resolve both city names to IATA codes robustly, then search flexible dates.
    """
    o = resolve_iata_robust(req.origin)
    if not o:
        raise HTTPException(400, f"Cannot resolve origin airport for '{req.origin}'.")

    d = resolve_iata_robust(req.destination)
    if not d:
        raise HTTPException(400, f"Cannot resolve destination airport for '{req.destination}'.")

    # Validate date
    try:
        td = datetime.strptime(req.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")
    if td < date.today():
        raise HTTPException(400, "Target date is in the past.")

    options = search_flexible(o, d, req.date, req.flex_days)
    if not options:
        return {
            "origin": o, "destination": d,
            "target_date": req.date, "flex_days": req.flex_days,
            "options": [], "cheapest_day": None,
            "target_price": None, "savings_if_flexible": 0,
            "message": (
                f"No flexible date data for {o}→{d}. "
                "Try a popular route like DEL↔BOM or BLR↔HYD."
            ),
        }

    target   = next((x for x in options if x.get("is_target")), None)
    cheapest = options[0]
    savings  = max(0, (target["price"] - cheapest["price"])) if target else 0

    return {
        "origin": o, "destination": d,
        "target_date": req.date, "flex_days": req.flex_days,
        "options": options, "cheapest_day": cheapest,
        "target_price": target["price"] if target else None,
        "savings_if_flexible": savings,
    }

@app.post("/budget")
def endpoint_budget(req: BudgetReq):
    """
    Resolve origin city to IATA, then search all destinations within budget.
    """
    o = resolve_iata_robust(req.origin)
    if not o:
        raise HTTPException(400, f"Cannot resolve origin airport for '{req.origin}'. "
                                 f"Try an IATA code (e.g. DEL for Delhi).")

    if req.budget_max <= req.budget_min:
        raise HTTPException(400, "Max budget must be greater than min budget.")

    dests = search_by_budget(
        origin=o,
        budget_max=req.budget_max,
        budget_min=req.budget_min,
        direct_only=req.direct_only,
        limit=50,
    )
    return {
        "origin": o,
        "budget_max": req.budget_max,
        "budget_min": req.budget_min,
        "destinations": dests,
        "count": len(dests),
        "message": "" if dests else (
            f"No destinations found from {o} in ₹{req.budget_min}–₹{req.budget_max} range. "
            "Try increasing max budget or use a major hub like DEL or BOM as origin."
        ),
    }

@app.post("/trend")
def endpoint_trend(req: TrendReq):
    o = resolve_iata_robust(req.origin) or req.origin.upper()
    d = resolve_iata_robust(req.destination) or req.destination.upper()
    monthly = get_monthly_cheapest(o, d)
    if not monthly:
        return {"origin":o,"destination":d,"trend":"unknown","monthly":[]}
    bp    = monthly[0]["price"]
    trend = classify_price_trend(o, d, bp)
    return {"origin":o,"destination":d,"best_price":bp,"trend":trend,"monthly":monthly}

@app.post("/compare")
def endpoint_compare(req: CompareReq):
    result = _run_search(req.origin, req.destination, req.date, req.radius_km)
    return {
        "search":           result["search"],
        "comparison_table": result["comparison_table"],
        "insights":         result["insights"],
    }

@app.post("/weather")
def endpoint_weather(req: WeatherReq):
    try:
        city_enc = req.city.replace(" ", "+")
        r = requests.get(
            f"https://wttr.in/{city_enc}?format=j1",
            headers={"User-Agent": "FarFinder/3.2"},
            timeout=8,
        )
        if r.status_code != 200:
            return {"city":req.city,"available":False,"message":"Weather unavailable."}
        data    = r.json()
        current = data.get("current_condition",[{}])[0]
        forecast = []
        for day in data.get("weather",[])[:3]:
            forecast.append({
                "date":   day.get("date",""),
                "max_c":  day.get("maxtempC",""),
                "min_c":  day.get("mintempC",""),
                "desc":   day.get("hourly",[{}])[4].get("weatherDesc",[{}])[0].get("value","") if day.get("hourly") else "",
            })
        return {
            "city":         req.city,
            "available":    True,
            "condition":    current.get("weatherDesc",[{}])[0].get("value","—"),
            "temp_c":       current.get("temp_C","—"),
            "feels_like_c": current.get("FeelsLikeC","—"),
            "humidity_pct": current.get("humidity","—"),
            "forecast":     forecast,
        }
    except Exception as e:
        return {"city":req.city,"available":False,"message":str(e)}

@app.post("/last-mile")
def endpoint_last_mile(req: LastMileReq):
    info = last_mile_info(req.iata.upper())
    return {"iata":req.iata.upper(),"info":info}