"""
Client for the free OSRM routing API (Open Source Routing Machine).

ONE request returns the full driving geometry, distance and duration:

    GET {base}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}
        ?overview=full&geometries=geojson&steps=false&alternatives=false

Any OSRM-compatible server works, so pointing OSRM_BASE_URL at a self-hosted
instance removes the public demo server's fair-use limits.
"""
from dataclasses import dataclass

import numpy as np
from django.conf import settings

from .errors import NoRouteError, UpstreamError
from .geo import METERS_PER_MILE
from .http import session


@dataclass
class Route:
    lats: np.ndarray
    lons: np.ndarray
    distance_miles: float
    duration_seconds: float


def fetch_route(start, finish):
    """`start` / `finish` are objects with .lat and .lon. Costs one HTTP call."""
    cfg = settings.FUEL_ROUTE
    url = (
        f"{cfg['OSRM_BASE_URL'].rstrip('/')}/route/v1/driving/"
        f"{start.lon:.6f},{start.lat:.6f};{finish.lon:.6f},{finish.lat:.6f}"
    )
    try:
        resp = session().get(
            url,
            params={
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
                "alternatives": "false",
            },
            timeout=cfg["HTTP_TIMEOUT_SECONDS"],
        )
        data = resp.json()
    except Exception as exc:
        raise UpstreamError(f"Routing service failed: {exc}") from exc

    code = data.get("code")
    if code == "NoRoute":
        raise NoRouteError("No drivable route exists between those two locations.")
    if code != "Ok" or not data.get("routes"):
        raise UpstreamError(f"Routing service error: {data.get('message') or code}")

    best = data["routes"][0]
    coords = np.asarray(best["geometry"]["coordinates"], dtype=float)  # [[lon, lat], ...]
    return Route(
        lats=coords[:, 1],
        lons=coords[:, 0],
        distance_miles=best["distance"] / METERS_PER_MILE,
        duration_seconds=best["duration"],
    )
