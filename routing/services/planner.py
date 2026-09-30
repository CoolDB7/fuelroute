"""
Orchestrates one /api/route/ request: geocode -> OSRM -> corridor search ->
optimizer -> a plain-dict response. Kept separate from the view so it's easy
to unit test without going through DRF/HTTP.
"""
from django.conf import settings

from . import geocoding, optimizer, osrm, stations
from .geo import cumulative_miles, thin_by_spacing


def plan_trip(start_text, finish_text):
    cfg = settings.FUEL_ROUTE

    start = geocoding.resolve(start_text)
    finish = geocoding.resolve(finish_text)

    route = osrm.fetch_route(start, finish)
    cum_miles = cumulative_miles(route.lats, route.lons)

    index = stations.get_index()
    candidates = index.near_route(route.lats, route.lons, cum_miles, cfg["CORRIDOR_MILES"])

    stops, total_cost = optimizer.plan_refuelling(
        route.distance_miles, candidates, cfg["MAX_RANGE_MILES"], cfg["MPG"]
    )

    keep = thin_by_spacing(cum_miles, cfg["RESPONSE_GEOMETRY_SPACING_MILES"])
    geometry = [[round(float(route.lats[i]), 5), round(float(route.lons[i]), 5)] for i in keep]

    fuel_stops = []
    for s in stops:
        row = index.rows[s.station_idx]
        fuel_stops.append(
            {
                "name": row.name,
                "address": row.address,
                "city": row.city,
                "state": row.state,
                "lat": row.latitude,
                "lon": row.longitude,
                "price_per_gallon": round(s.price, 3),
                "mile_marker": round(s.mile, 1),
                "gallons_purchased": round(s.gallons_purchased, 2),
                "cost": round(s.cost, 2),
            }
        )

    total_gallons_purchased = sum(s.gallons_purchased for s in stops)

    return {
        "start": start.as_dict(),
        "finish": finish.as_dict(),
        "distance_miles": round(route.distance_miles, 1),
        "duration_hours": round(route.duration_seconds / 3600, 2),
        "vehicle_assumptions": {
            "max_range_miles": cfg["MAX_RANGE_MILES"],
            "mpg": cfg["MPG"],
            "starts_with_a_full_tank": True,
        },
        "fuel_stops": fuel_stops,
        "total_trip_gallons": round(route.distance_miles / cfg["MPG"], 2),
        "total_gallons_purchased": round(total_gallons_purchased, 2),
        "total_fuel_cost_usd": round(total_cost, 2),
        "route_geometry": geometry,
        "external_calls_made": (
            1  # OSRM
            + start.external_calls
            + finish.external_calls
        ),
    }
