"""
routes.py — Multi-modal route builder (single build_routes function)
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed

from airports import ground_transport, last_mile_info, intercity_ground_routes
from flights  import search_best, search_connecting_via_hubs, get_latest_prices, booking_links

AIRPORT_BUFFER_MIN = 90

def build_routes(
    nearby_airports: list[dict],
    dest_airport: dict,
    departure_date: str,
    origin_city: str,
    adults: int = 1,
    max_workers: int = 10,
    max_flights_per_airport: int = 8,
) -> list[dict]:
    dest_iata = dest_airport["iata"]
    dest_city = dest_airport.get("city") or dest_airport.get("name","Destination")
    all_routes: list[dict] = []
    lm_info = last_mile_info(dest_iata)

    def _one_airport(ap: dict) -> list[dict]:
        iata   = ap["iata"]
        dist   = float(ap.get("distance_km",0))
        ground = ground_transport(dist)

        flights = search_best(iata, dest_iata, departure_date,
                              max_results=max_flights_per_airport*3)
        if not flights:
            flights = get_latest_prices(iata, dest_iata, limit=20)

        connecting = search_connecting_via_hubs(iata, dest_iata, departure_date)

        all_flights = list(flights)
        seen_keys: set[tuple] = {
            (f.get("carrier_code",""),int(f.get("stops",0) or 0),int(f.get("price_inr",0) or 0))
            for f in all_flights
        }
        for cf in connecting:
            key = (cf.get("carrier_code",""),int(cf.get("stops",0) or 0),int(cf.get("price_inr",0) or 0))
            if key not in seen_keys:
                seen_keys.add(key); all_flights.append(cf)

        if not all_flights: return []

        local: list[dict] = []
        local_seen: set[tuple] = set()

        for flight in all_flights[:max_flights_per_airport*2]:
            key = (
                flight.get("carrier_code") or flight.get("carrier",""),
                int(flight.get("stops",0) or 0),
                flight.get("dep_date",""),
                int(flight.get("price_inr",0) or 0),
            )
            if key in local_seen: continue
            local_seen.add(key)

            flight_dur   = int(flight.get("duration_min") or 90)
            flight_price = int(flight.get("price_inr",0) or 0)
            ground_cost  = int(ground.get("cost_inr",0))
            ground_time  = int(ground.get("time_min",0))
            lm_cost      = lm_info["cheapest_cost"]
            lm_time      = lm_info["cheapest_mins"]

            total_cost = flight_price + ground_cost + lm_cost
            total_time = ground_time + flight_dur + AIRPORT_BUFFER_MIN + lm_time

            is_home    = dist <= 5.0
            dep_date   = flight.get("dep_date") or departure_date
            source     = str(flight.get("source","")).lower()
            conn_via   = flight.get("connecting_via","")

            confidence = "high" if (is_home and source not in {"latest","fallback"}) \
                         else "medium" if not is_home else "low"

            # Journey breakdown
            journey = []
            if dist > 0.4:
                journey.append({
                    "step":  f"{origin_city} → {ap['city']} Airport",
                    "desc":  ground["note"],
                    "mode":  ground["mode"],
                    "emoji": ground["emoji"],
                    "cost":  ground_cost,
                    "time":  ground_time,
                })
            if conn_via:
                for leg in flight.get("legs",[]):
                    f2 = leg.get("flight",{})
                    journey.append({
                        "step":  f"Flight {leg.get('from',iata)} → {leg.get('to',conn_via)}",
                        "desc":  f"{f2.get('carrier','?')} · {f2.get('stops',0)} stop(s)",
                        "mode":  "flight","emoji":"✈️",
                        "cost":  int(f2.get("price_inr",0) or 0),
                        "time":  int(f2.get("duration_min",0) or 90),
                    })
            else:
                journey.append({
                    "step":  f"Flight {iata} → {dest_iata}",
                    "desc":  f"{flight.get('carrier','?')} · {flight.get('dep_date','')}",
                    "mode":  "flight","emoji":"✈️",
                    "cost":  flight_price,
                    "time":  flight_dur,
                })
            lm_mode = lm_info["cheapest_mode"]
            journey.append({
                "step":  f"{dest_iata} Airport → {dest_city}",
                "desc":  lm_mode["label"],
                "mode":  lm_mode["mode"],"emoji":lm_mode["emoji"],
                "cost":  lm_cost,"time":lm_time,
            })

            local.append({
                "route_type":    "direct" if is_home else "multimodal",
                "origin_city":   origin_city,
                "origin_airport": {
                    "iata":iata,"name":ap.get("name",iata),
                    "city":ap.get("city",origin_city),
                    "distance_km":round(dist,1),"country":ap.get("country",""),
                },
                "destination": {"iata":dest_iata,"city":dest_city,"name":dest_airport.get("name",dest_city)},
                "ground":      ground,
                "last_mile":   {"cost":lm_cost,"mins":lm_time,"km":lm_info["km"],"note":lm_mode["label"]},
                "last_mile_modes": lm_info["modes"],
                "flight":      flight,
                "connecting_via": conn_via,
                "total_cost_inr": total_cost,
                "total_time_min": total_time,
                "savings_inr":    0,
                "confidence":     confidence,
                "fallback_used":  source in {"latest","fallback"},
                "booking_links":  booking_links(iata, dest_iata, dep_date, adults),
                "journey_breakdown": journey,
            })

            if len(local) >= max_flights_per_airport: break

        return local

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_one_airport, ap) for ap in nearby_airports]
        for fut in as_completed(futures):
            try: all_routes.extend(fut.result())
            except Exception as e: print(f"⚠️  Route error: {e}")

    if not all_routes: return []

    all_routes.sort(key=lambda x: (x["total_cost_inr"], x["total_time_min"]))

    home_routes = [r for r in all_routes if r["route_type"] == "direct"]
    ref_cost = home_routes[0]["total_cost_inr"] if home_routes else all_routes[0]["total_cost_inr"]
    for r in all_routes:
        r["savings_inr"] = max(0, ref_cost - r["total_cost_inr"])

    return all_routes[:80]

def build_comparison_table(routes: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in routes:
        iata = r["origin_airport"]["iata"] if r.get("route_type") != "ground_only" else f"GROUND_{r['ground']['mode']}"
        if iata in seen: continue
        seen[iata] = {
            "iata":        iata,
            "city":        r["origin_airport"]["city"],
            "country":     r["origin_airport"].get("country",""),
            "distance_km": r["origin_airport"].get("distance_km",0),
            "ground_mode": r["ground"]["mode"],
            "ground_emoji":r["ground"]["emoji"],
            "ground_cost": r["ground"]["cost_inr"],
            "ground_time": r["ground"]["time_min"],
            "flight_price":r["flight"]["price_inr"] if r.get("flight") else 0,
            "last_mile":   r.get("last_mile",{}).get("cost",0),
            "carrier":     r["flight"]["carrier"] if r.get("flight") else "—",
            "stops":       r["flight"]["stops"] if r.get("flight") else 0,
            "total_cost":  r["total_cost_inr"],
            "savings":     r.get("savings_inr",0),
            "route_type":  r["route_type"],
            "dep_date":    r["flight"].get("dep_date","") if r.get("flight") else "",
        }
    table = sorted(seen.values(), key=lambda x: x["total_cost"])
    for i, row in enumerate(table, 1):
        row["rank"] = i
    return table

def build_airport_comparison(routes: list[dict]) -> list[dict]:
    return build_comparison_table(routes)

def generate_insights(routes: list[dict]) -> list[str]:
    if not routes:
        return ["No options found. Try a wider radius or a different date."]
    insights: list[str] = []
    best = min(routes, key=lambda r: r["total_cost_inr"])
    dest_city = best["destination"]["city"]
    insights.append(
        f"💸 **Best deal: {best['origin_airport']['city']} → {dest_city}** "
        f"· ₹{best['total_cost_inr']:,} all-inclusive"
        f"{' · '+best['flight']['carrier'] if best.get('flight') else ''}"
    )
    nonstop = [r for r in routes if r.get("flight") and r["flight"]["stops"] == 0]
    if nonstop:
        ns = min(nonstop, key=lambda r: r["total_cost_inr"])
        insights.append(
            f"✈️  Cheapest **non-stop**: {ns['origin_airport']['city']} → {dest_city} "
            f"· ₹{ns['total_cost_inr']:,} · {ns['flight']['carrier']}"
        )
    savers = [r for r in routes if r.get("savings_inr",0) > 500]
    if savers:
        top = max(savers, key=lambda r: r["savings_inr"])
        insights.append(
            f"🚌 **Multi-modal win**: Reach **{top['origin_airport']['city']}** by "
            f"{top['ground']['emoji']} {top['ground']['mode']} "
            f"({top['origin_airport']['distance_km']} km) → save **₹{top['savings_inr']:,}**"
        )
    ground_only = [r for r in routes if r.get("route_type") == "ground_only"]
    if ground_only:
        go = min(ground_only, key=lambda r: r["total_cost_inr"])
        h, m = divmod(go["total_time_min"], 60)
        insights.append(
            f"🚂 **Ground option**: {go['ground']['mode'].title()} all the way "
            f"· ₹{go['total_cost_inr']:,} · {h}h {m}m"
        )
    fastest = min(routes, key=lambda r: r["total_time_min"])
    fh, fm  = divmod(fastest["total_time_min"], 60)
    if fastest is not best:
        insights.append(
            f"⚡ **Fastest**: {fh}h {fm}m via **{fastest['origin_airport']['city']}** "
            f"· ₹{fastest['total_cost_inr']:,}"
        )
    n_ap = len({r["origin_airport"]["iata"] for r in routes})
    insights.append(f"🗺️  **{n_ap} airports** checked · **{len(routes)} routes** found")
    return insights