"""
routes.py — Multi-modal route builder + ranker

For each airport in radius:
  total_cost = flight_price + ground_transport_to_airport
  total_time = flight_duration + ground_time + AIRPORT_BUFFER

Routes are ranked by total cost.
Savings computed vs cheapest same-city direct flight.
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed

from airports import ground_transport
from flights import (
    search_cheap, search_direct, get_latest_prices,
    classify_price_trend, build_booking_link,
)

AIRPORT_BUFFER_MIN = 90   # check-in + security + boarding


# ─────────────────────────────────────────────────────────────────────────────
#  CORE ROUTE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_routes(
    nearby_airports: list[dict],
    dest_airport:    dict,
    departure_date:  str,
    origin_city:     str,
    adults:          int = 1,
    max_workers:     int = 8,
) -> list[dict]:
    """
    Search flights from every nearby airport in parallel.
    Returns flat list of route dicts, sorted by total_cost_inr.
    """
    dest_iata = dest_airport["iata"]
    dest_city = dest_airport.get("city", "Destination")
    routes: list[dict] = []

    def _search_one_airport(ap: dict) -> list[dict]:
        iata    = ap["iata"]
        dist    = ap["distance_km"]
        ground  = ground_transport(dist)

        # Try cheap first, fallback to latest prices
        flights = search_cheap(iata, dest_iata, departure_date)
        if not flights:
            flights = get_latest_prices(iata, dest_iata)
        if not flights:
            flights = search_direct(iata, dest_iata, departure_date)

        local_routes = []
        for flight in flights:
            ground_cost = ground["cost_inr"]
            ground_time = ground["time_min"]
            total_cost  = flight["price_inr"] + ground_cost
            total_time  = (flight["duration_min"] or 90) + ground_time + AIRPORT_BUFFER_MIN
            is_home     = dist <= 5.0

            # Build booking links
            dep_date = flight.get("dep_date") or departure_date
            links    = build_booking_link(iata, dest_iata, dep_date, adults)

            local_routes.append({
                "route_type":    "direct" if is_home else "multimodal",
                "origin_city":   origin_city,
                "origin_airport": {
                    "iata":        iata,
                    "name":        ap["name"],
                    "city":        ap["city"],
                    "country":     ap.get("country", ""),
                    "distance_km": dist,
                },
                "destination": {
                    "iata": dest_iata,
                    "city": dest_city,
                    "name": dest_airport["name"],
                },
                "ground":        ground,
                "flight":        flight,
                "total_cost_inr": total_cost,
                "total_time_min": total_time,
                "savings_inr":   0,            # filled after sort
                "booking_links": links,
                "summary":       _summary(
                    origin_city, is_home, ap, ground, flight,
                    dest_city, total_cost, total_time
                ),
            })
        return local_routes

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_search_one_airport, ap): ap for ap in nearby_airports}
        for fut in as_completed(futures):
            try:
                routes.extend(fut.result())
            except Exception as e:
                print(f"⚠️  Route error: {e}")

    if not routes:
        return []

    # Sort cheapest first
    routes.sort(key=lambda r: r["total_cost_inr"])

    # Compute savings vs cheapest home-airport route
    home_routes = [r for r in routes if r["route_type"] == "direct"]
    ref_cost = home_routes[0]["total_cost_inr"] if home_routes else routes[0]["total_cost_inr"]
    for r in routes:
        r["savings_inr"] = max(0, ref_cost - r["total_cost_inr"])

    return routes


# ─────────────────────────────────────────────────────────────────────────────
#  AIRPORT COMPARISON TABLE
# ─────────────────────────────────────────────────────────────────────────────

def build_airport_comparison(routes: list[dict]) -> list[dict]:
    """
    Group routes by origin airport and return one row per airport
    with its cheapest price, ground cost, total, and savings.
    """
    seen: dict[str, dict] = {}
    for r in routes:
        iata = r["origin_airport"]["iata"]
        if iata not in seen:
            seen[iata] = {
                "iata":        iata,
                "city":        r["origin_airport"]["city"],
                "distance_km": r["origin_airport"]["distance_km"],
                "ground_mode": r["ground"]["mode"],
                "ground_cost": r["ground"]["cost_inr"],
                "ground_time": r["ground"]["time_min"],
                "flight_price":r["flight"]["price_inr"],
                "total_cost":  r["total_cost_inr"],
                "savings":     r["savings_inr"],
                "carrier":     r["flight"]["carrier"],
                "stops":       r["flight"]["stops"],
                "route_type":  r["route_type"],
            }
    table = sorted(seen.values(), key=lambda x: x["total_cost"])
    # Rank
    for i, row in enumerate(table, 1):
        row["rank"] = i
    return table


# ─────────────────────────────────────────────────────────────────────────────
#  INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────

def generate_insights(routes: list[dict]) -> list[str]:
    """Generate 3-5 human-readable insight strings for the search results."""
    if not routes:
        return ["No flights found. Try a wider radius or a different date."]

    insights: list[str] = []
    best = routes[0]

    # Best deal
    insights.append(
        f"💸 Best deal: ₹{best['total_cost_inr']:,} via **{best['origin_airport']['city']}** "
        f"({best['flight']['carrier']}, {best['flight']['stops_label']})"
    )

    # Best non-stop
    nonstop = [r for r in routes if r["flight"]["stops"] == 0]
    if nonstop:
        ns = nonstop[0]
        insights.append(
            f"✈️  Cheapest non-stop: ₹{ns['total_cost_inr']:,} from "
            f"**{ns['origin_airport']['city']}** ({ns['flight']['carrier']})"
        )

    # Top multi-modal saver
    savers = [r for r in routes if r["savings_inr"] > 500]
    if savers:
        top = max(savers, key=lambda r: r["savings_inr"])
        insights.append(
            f"🚌 Multi-modal win: Fly from **{top['origin_airport']['city']}** "
            f"({top['ground']['emoji']} {top['origin_airport']['distance_km']} km) "
            f"→ save **₹{top['savings_inr']:,}** vs flying direct"
        )

    # Fastest
    fastest = min(routes, key=lambda r: r["total_time_min"])
    fh, fm  = divmod(fastest["total_time_min"], 60)
    if fastest["origin_airport"]["iata"] != best["origin_airport"]["iata"]:
        insights.append(
            f"⚡ Fastest door-to-door: {fh}h {fm}m via "
            f"**{fastest['origin_airport']['city']}** (₹{fastest['total_cost_inr']:,})"
        )

    # Unique airports found
    airport_count = len({r["origin_airport"]["iata"] for r in routes})
    insights.append(f"🗺️  Checked **{airport_count}** airports within radius — {len(routes)} route options found")

    return insights


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY  (single-line description of a route)
# ─────────────────────────────────────────────────────────────────────────────

def _summary(
    origin_city: str, is_home: bool, ap: dict,
    ground: dict, flight: dict,
    dest_city: str, total_cost: int, total_time: int,
) -> str:
    h, m = divmod(total_time, 60)
    time_str = f"{h}h {m}m"
    if is_home:
        return (
            f"{origin_city}({ap['iata']}) → {dest_city} | "
            f"{flight['carrier']} | {flight['stops_label']} | "
            f"₹{total_cost:,} | {time_str}"
        )
    return (
        f"{origin_city} → [{ground['mode']} {ap['distance_km']}km] → "
        f"{ap['city']}({ap['iata']}) → {dest_city} | "
        f"{flight['carrier']} | ₹{total_cost:,} | {time_str}"
    )
