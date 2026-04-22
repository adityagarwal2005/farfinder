"""
agent.py — FarFinder v2 FastAPI backend

Run:
  pip install fastapi uvicorn requests pydantic
  uvicorn agent:app --reload --port 8001

Env vars:
  TRAVELPAYOUTS_TOKEN  — your token (default: hardcoded)
  OPENROUTER_API_KEY   — for NL query parsing (optional, regex fallback used if absent)

Endpoints:
  GET  /health
  POST /search           — structured multi-modal search
  POST /search-nl        — natural language → parse → search
  POST /parse-query      — only parse NL, don't search
  POST /calendar         — price calendar for a route+month
  POST /flexible         — cheapest ±N days around a target date
  POST /budget           — find destinations reachable within a budget
  POST /compare          — comparison table of airports in radius
  POST /trend            — price trend (cheap / normal / expensive)
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from airports import (
    geocode_location, find_airports_in_radius,
    resolve_destination_airport, city_to_iata,
)
from flights import (
    get_price_calendar, search_flexible,
    search_by_budget, get_monthly_cheapest,
    classify_price_trend,
)
from routes import build_routes, generate_insights, build_airport_comparison

# ─────────────────────────────────────────────────────────────────────────────
#  APP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="FarFinder v2 — Multi-Modal Flight Agent",
    description="Powered by Travelpayouts Data API · Finds cheapest flights from nearby airports",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")


# ─────────────────────────────────────────────────────────────────────────────
#  PYDANTIC MODELS
# ─────────────────────────────────────────────────────────────────────────────

class SearchReq(BaseModel):
    origin:      str
    destination: str
    date:        str
    radius_km:   float = Field(default=100.0, ge=10, le=500)
    adults:      int   = Field(default=1, ge=1, le=9)
    direct_only: bool  = False

    @validator('origin', 'destination')
    def validate_cities(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('City name must be at least 2 characters')
        return v.strip()

    @validator('date')
    def validate_date(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')
        return v

class NLReq(BaseModel):
    query: str

    @validator('query')
    def validate_query(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError('Query must be at least 5 characters')
        return v.strip()

class CalendarReq(BaseModel):
    origin:      str
    destination: str
    month:       str

    @validator('origin', 'destination')
    def validate_cities(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('City name must be at least 2 characters')
        return v.strip()

    @validator('month')
    def validate_month(cls, v):
        try:
            datetime.strptime(v, '%Y-%m')
        except ValueError:
            raise ValueError('Month must be in YYYY-MM format')
        return v

class FlexibleReq(BaseModel):
    origin:      str
    destination: str
    date:        str
    flex_days:   int = Field(default=3, ge=1, le=14)

    @validator('origin', 'destination')
    def validate_cities(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('City name must be at least 2 characters')
        return v.strip()

    @validator('date')
    def validate_date(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')
        return v

class BudgetReq(BaseModel):
    origin:      str
    budget_max:  int   = Field(default=5000, ge=100, le=100000)
    budget_min:  int   = Field(default=0, ge=0, le=100000)
    currency:    str   = "inr"
    direct_only: bool  = False

    @validator('origin')
    def validate_city(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('City name must be at least 2 characters')
        return v.strip()

    @validator('budget_max')
    def validate_budget(cls, v, values):
        if 'budget_min' in values and v < values['budget_min']:
            raise ValueError('Max budget must be ≥ min budget')
        return v

class CompareReq(BaseModel):
    origin:      str
    destination: str
    date:        str
    radius_km:   float = Field(default=150.0, ge=10, le=500)

    @validator('origin', 'destination')
    def validate_cities(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('City name must be at least 2 characters')
        return v.strip()

    @validator('date')
    def validate_date(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')
        return v

class TrendReq(BaseModel):
    origin:      str
    destination: str

    @validator('origin', 'destination')
    def validate_cities(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('City name must be at least 2 characters')
        return v.strip()


# ─────────────────────────────────────────────────────────────────────────────
#  NL PARSER
# ─────────────────────────────────────────────────────────────────────────────

_PARSE_PROMPT = """You are a flight search query parser. Today is {today}.

Extract and return ONLY this JSON (no markdown, no extra text):
{{
  "origin":      "city name or unknown",
  "destination": "city name or unknown",
  "date":        "YYYY-MM-DD or empty",
  "radius_km":   <number>,
  "adults":      <number>,
  "direct_only": <true|false>,
  "flex_days":   <0 if not flexible, else N>,
  "confidence":  "high|medium|low",
  "note":        "any info"
}}

RULES:
- Indian city aliases: Bombay=Mumbai, Calcutta=Kolkata, Madras=Chennai, Dilli=Delhi, Bengaluru=Bangalore
- Radius keywords: "nearby"=50, "wide"=300, "within X km"=X, absent=100
- "non-stop" or "direct only" → direct_only=true
- "flexible" or "±N days" → flex_days=N (default 3)
- If date unclear → 7 days from today
- Hinglish: "Dilli se Mumbai 15 April 200km mein" → origin=Delhi, destination=Mumbai, radius=200

QUERY: "{query}"
"""


def parse_nl(query: str) -> dict:
    if not OPENROUTER_KEY:
        return _regex_parse(query)
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":           "deepseek/deepseek-chat",
                "messages":        [{"role": "user", "content":
                    _PARSE_PROMPT.format(today=date.today().isoformat(), query=query)}],
                "temperature":     0.1,
                "max_tokens":      250,
                "response_format": {"type": "json_object"},
            },
            timeout=18,
        )
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"⚠️  LLM parse failed ({e}), using regex")
        return _regex_parse(query)


def _regex_parse(q: str) -> dict:
    ql = q.lower()
    radius = 100.0
    if m := re.search(r"(\d+)\s*km", ql):
        radius = float(m.group(1))
    travel_date = (date.today() + timedelta(days=7)).isoformat()
    if "tomorrow" in ql:
        travel_date = (date.today() + timedelta(days=1)).isoformat()
    elif "next week" in ql:
        travel_date = (date.today() + timedelta(days=7)).isoformat()
    elif m := re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-]?(\d{2,4})?", ql):
        try:
            d, mo = int(m.group(1)), int(m.group(2))
            yr = int(m.group(3)) if m.group(3) else date.today().year
            yr = yr if yr > 99 else 2000 + yr
            travel_date = date(yr, mo, d).isoformat()
        except ValueError:
            pass

    origin, destination = "unknown", "unknown"
    if " to " in ql:
        parts = ql.split(" to ", 1)
        destination = parts[1].strip().split()[0].title()
        for kw in ["from", "fly", "travel"]:
            if kw in parts[0]:
                origin = parts[0].split(kw)[-1].strip().split()[0].title()
                break
    elif " se " in ql:
        parts = ql.split(" se ", 1)
        origin      = parts[0].strip().split()[-1].title()
        destination = parts[1].strip().split()[0].title()

    direct_only = any(w in ql for w in ["non-stop", "nonstop", "direct only"])
    flex_days   = 3 if "flex" in ql else 0

    return {
        "origin": origin, "destination": destination, "date": travel_date,
        "radius_km": radius, "adults": 1, "direct_only": direct_only,
        "flex_days": flex_days, "confidence": "low",
        "note": "Regex fallback — set OPENROUTER_API_KEY for smarter parsing",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  SHARED SEARCH PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def _run_search(
    origin: str, destination: str,
    travel_date: str, radius_km: float,
    adults: int = 1, direct_only: bool = False,
) -> dict:
    start_time = time.time()

    # Validate date
    try:
        td = datetime.strptime(travel_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD. Example: 2026-04-15"
        )
    if td < date.today():
        raise HTTPException(
            status_code=400,
            detail=f"Travel date cannot be in the past. Today is {date.today().isoformat()}. Please choose a future date."
        )

    # Geocode origin
    try:
        coords = geocode_location(origin)
        if not coords:
            raise ValueError()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not locate '{origin}'. Try spelling it differently or use a nearby major city."
        )
    olat, olon = coords

    # Airports in radius
    nearby = find_airports_in_radius(olat, olon, radius_km)
    if not nearby:
        suggestions = "Try increasing radius_km parameter" if radius_km < 200 else "No major airports found in this region"
        raise HTTPException(
            status_code=404,
            detail=f"No airports found within {radius_km} km of {origin}. {suggestions}. Minimum radius: 10 km, Maximum: 500 km."
        )

    # Destination airport
    try:
        dest_ap = resolve_destination_airport(destination)
        if not dest_ap:
            raise ValueError()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not find '{destination}' airport. Try spelling it differently or use IATA code (e.g., BOM, DEL, BLR)."
        )

    # Build routes
    try:
        routes = build_routes(
            nearby_airports=nearby,
            dest_airport=dest_ap,
            departure_date=travel_date,
            origin_city=origin.title(),
            adults=adults,
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Flight data service temporarily unavailable. {str(e)} Please try again in a few moments."
        )

    # Filter if direct_only
    if direct_only:
        routes = [r for r in routes if r["flight"]["stops"] == 0]
        if not routes:
            raise HTTPException(
                status_code=404,
                detail=f"No non-stop flights found. {len(nearby)} airports checked. Try removing direct_only filter or expanding search radius."
            )

    insights   = generate_insights(routes)
    comparison = build_airport_comparison(routes)

    # Monthly cheapest for context
    origin_iata = nearby[0]["iata"]
    try:
        monthly = get_monthly_cheapest(origin_iata, dest_ap["iata"])
    except Exception:
        monthly = []

    elapsed = time.time() - start_time

    return {
        "search": {
            "origin": origin.title(), "origin_lat": round(olat, 4), "origin_lon": round(olon, 4),
            "destination": destination.title(), "date": travel_date,
            "radius_km": radius_km, "adults": adults, "direct_only": direct_only,
        },
        "metadata": {
            "search_time_seconds": round(elapsed, 2),
            "airports_checked":    len(nearby),
            "results_found":       len(routes),
            "timestamp":           datetime.now().isoformat(),
        },
        "nearby_airports":     nearby,
        "destination_airport": dest_ap,
        "total_routes":        len(routes),
        "routes":              routes[:25],
        "comparison_table":    comparison,
        "insights":            insights,
        "monthly_cheapest":    monthly,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "FarFinder v2", "api": "Travelpayouts Data API"}


@app.post("/parse-query")
def endpoint_parse(req: NLReq):
    return {"query": req.query, "parsed": parse_nl(req.query)}


@app.post("/search")
def endpoint_search(req: SearchReq):
    return _run_search(req.origin, req.destination, req.date, req.radius_km, req.adults, req.direct_only)


@app.post("/search-nl")
def endpoint_search_nl(req: NLReq):
    parsed = parse_nl(req.query)
    if parsed.get("origin", "unknown").lower() == "unknown":
        raise HTTPException(
            status_code=400,
            detail="Could not detect departure city. Examples: 'From Delhi to Mumbai', 'Bangalore to Goa tomorrow', 'Kolkata se Chennai 200km 15 April'"
        )
    if parsed.get("destination", "unknown").lower() == "unknown":
        raise HTTPException(
            status_code=400,
            detail="Could not detect destination city. Example: 'Delhi to Goa on 20 April'"
        )
    result = _run_search(
        origin=parsed["origin"], destination=parsed["destination"],
        travel_date=parsed.get("date") or (date.today() + timedelta(days=7)).isoformat(),
        radius_km=float(parsed.get("radius_km", 100)),
        adults=int(parsed.get("adults", 1)),
        direct_only=bool(parsed.get("direct_only", False)),
    )
    result["parsed_query"] = parsed
    # If flex_days > 0, append flexible results
    if int(parsed.get("flex_days", 0)) > 0:
        try:
            origin_iata = result["nearby_airports"][0]["iata"]
            dest_iata   = result["destination_airport"]["iata"]
            flex = search_flexible(
                origin_iata, dest_iata,
                parsed.get("date") or result["search"]["date"],
                int(parsed["flex_days"]),
            )
            result["flexible_dates"] = flex
        except Exception:
            pass
    return result


@app.post("/calendar")
def endpoint_calendar(req: CalendarReq):
    """Return price calendar (price per day) for origin→dest in given month."""
    try:
        origin_iata = city_to_iata(req.origin) or req.origin.upper()
        dest_iata   = city_to_iata(req.destination) or req.destination.upper()

        # If city names given, try to resolve
        if len(origin_iata) != 3:
            coords = geocode_location(req.origin)
            if coords:
                nearby = find_airports_in_radius(*coords, 60)
                origin_iata = nearby[0]["iata"] if nearby else origin_iata
            else:
                raise HTTPException(400, f"Could not locate '{req.origin}' airport.")

        if len(dest_iata) != 3:
            dest_ap = resolve_destination_airport(req.destination)
            if dest_ap:
                dest_iata = dest_ap["iata"]
            else:
                raise HTTPException(400, f"Could not locate '{req.destination}' airport.")

        calendar = get_price_calendar(origin_iata, dest_iata, req.month)

        if not calendar:
            return {
                "origin": origin_iata, "destination": dest_iata,
                "month": req.month, "calendar": {}, "cheapest_day": None,
                "note": "No price data available for this route+month. Try adjacent months."
            }

        cheapest_day = min(calendar.items(), key=lambda x: x[1]["price"])
        return {
            "origin":      origin_iata,
            "destination": dest_iata,
            "month":       req.month,
            "calendar":    calendar,
            "cheapest_day": {
                "date":    cheapest_day[0],
                "price":   cheapest_day[1]["price"],
                "airline": cheapest_day[1]["airline"],
            },
            "days_with_data": len(calendar),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Calendar service temporarily unavailable. {str(e)}"
        )


@app.post("/flexible")
def endpoint_flexible(req: FlexibleReq):
    """Find cheapest day within ±flex_days of the target date."""
    try:
        origin_iata = city_to_iata(req.origin) or req.origin.upper()
        dest_iata   = city_to_iata(req.destination) or req.destination.upper()

        if len(origin_iata) != 3:
            coords = geocode_location(req.origin)
            if coords:
                nearby = find_airports_in_radius(*coords, 60)
                origin_iata = nearby[0]["iata"] if nearby else origin_iata
            else:
                raise HTTPException(400, f"Could not locate '{req.origin}' airport.")

        if len(dest_iata) != 3:
            dest_ap = resolve_destination_airport(req.destination)
            if dest_ap:
                dest_iata = dest_ap["iata"]
            else:
                raise HTTPException(400, f"Could not locate '{req.destination}' airport.")

        results = search_flexible(origin_iata, dest_iata, req.date, req.flex_days)
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No flexible date options found for {origin_iata} → {dest_iata}. Try a different date."
            )
        
        target_entry = next((r for r in results if r["is_target"]), None)
        cheapest     = results[0] if results else None

        savings = 0
        if target_entry and cheapest and target_entry["price"] != cheapest["price"]:
            savings = target_entry["price"] - cheapest["price"]

        return {
            "origin":       origin_iata,
            "destination":  dest_iata,
            "target_date":  req.date,
            "flex_days":    req.flex_days,
            "options":      results,
            "cheapest_day": cheapest,
            "target_price": target_entry["price"] if target_entry else None,
            "savings_if_flexible": savings,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Flexible dates service temporarily unavailable. {str(e)}"
        )


@app.post("/budget")
def endpoint_budget(req: BudgetReq):
    """Find all destinations reachable from origin within budget."""
    try:
        origin_iata = city_to_iata(req.origin) or req.origin.upper()
        if len(origin_iata) != 3:
            coords = geocode_location(req.origin)
            if coords:
                nearby = find_airports_in_radius(*coords, 60)
                origin_iata = nearby[0]["iata"] if nearby else origin_iata
            else:
                raise HTTPException(400, f"Could not locate '{req.origin}' airport.")

        destinations = search_by_budget(
            origin=origin_iata,
            budget_min=req.budget_min,
            budget_max=req.budget_max,
            currency=req.currency,
            direct_only=req.direct_only,
        )
        
        if not destinations:
            suggestion = "Try increasing max budget or removing direct-only filter" if req.direct_only else "Try increasing max budget"
            return {
                "origin":       origin_iata,
                "budget_max":   req.budget_max,
                "budget_min":   req.budget_min,
                "currency":     req.currency,
                "destinations": [],
                "count":        0,
                "note":         f"No destinations found within budget. {suggestion}."
            }
        
        return {
            "origin":       origin_iata,
            "budget_max":   req.budget_max,
            "budget_min":   req.budget_min,
            "currency":     req.currency,
            "destinations": destinations,
            "count":        len(destinations),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Budget finder service temporarily unavailable. {str(e)}"
        )


@app.post("/compare")
def endpoint_compare(req: CompareReq):
    """Return airport comparison table without full route details."""
    result = _run_search(req.origin, req.destination, req.date, req.radius_km)
    return {
        "search":           result["search"],
        "comparison_table": result["comparison_table"],
        "insights":         result["insights"],
    }


@app.post("/trend")
def endpoint_trend(req: TrendReq):
    """Check if a route's prices are currently cheap / normal / expensive."""
    origin_iata = city_to_iata(req.origin) or req.origin.upper()
    dest_iata   = city_to_iata(req.destination) or req.destination.upper()

    monthly = get_monthly_cheapest(origin_iata, dest_iata)
    if not monthly:
        return {"origin": origin_iata, "destination": dest_iata, "trend": "unknown", "monthly": []}

    best_price = monthly[0]["price"] if monthly else 0
    trend      = classify_price_trend(origin_iata, dest_iata, best_price)

    return {
        "origin":      origin_iata,
        "destination": dest_iata,
        "best_price":  best_price,
        "trend":       trend,
        "monthly":     monthly,
    }
