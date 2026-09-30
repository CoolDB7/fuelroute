"""
In-memory station index.

The ~6.6k stations are read from SQLite ONCE per process into numpy arrays.
After that a request never touches the database: candidate stations for a route
are found with vectorised maths.
"""
import threading
from dataclasses import dataclass

import numpy as np

from ..models import FuelStation
from .geo import haversine_miles

_lock = threading.Lock()
_index = None


@dataclass
class Candidate:
    """A station near the route, positioned by how far along the route it is."""

    station_idx: int
    mile: float  # miles from the start of the route
    offset_miles: float  # straight-line distance from the route
    price: float


class StationIndex:
    def __init__(self, rows):
        self.rows = rows  # list of FuelStation
        self.lat = np.array([r.latitude for r in rows])
        self.lon = np.array([r.longitude for r in rows])
        self.price = np.array([float(r.price) for r in rows])

    def near_route(self, route_lats, route_lons, route_cum_miles, corridor_miles):
        """
        Return Candidates within `corridor_miles` of the route.

        Steps: (1) cheap bounding-box cut, (2) exact distance from each
        remaining station to a ~1-mile-spaced sample of the route, in chunks so
        memory stays small. Nearest sample point gives both the offset from the
        route and the station's mile marker along it.
        """
        pad = corridor_miles / 60.0  # degrees of latitude ~ 69 mi; deliberately generous
        lat_pad = pad
        lon_pad = pad / max(np.cos(np.radians(np.mean(route_lats))), 0.2)
        in_box = (
            (self.lat >= route_lats.min() - lat_pad)
            & (self.lat <= route_lats.max() + lat_pad)
            & (self.lon >= route_lons.min() - lon_pad)
            & (self.lon <= route_lons.max() + lon_pad)
        )
        idx = np.flatnonzero(in_box)
        if idx.size == 0:
            return []

        out = []
        for start in range(0, idx.size, 400):
            chunk = idx[start : start + 400]
            d = haversine_miles(
                self.lat[chunk, None], self.lon[chunk, None],
                route_lats[None, :], route_lons[None, :],
            )
            nearest = d.argmin(axis=1)
            offset = d[np.arange(chunk.size), nearest]
            for k in np.flatnonzero(offset <= corridor_miles):
                out.append(
                    Candidate(
                        station_idx=int(chunk[k]),
                        mile=float(route_cum_miles[nearest[k]]),
                        offset_miles=float(offset[k]),
                        price=float(self.price[chunk[k]]),
                    )
                )
        out.sort(key=lambda c: c.mile)
        return out


def get_index():
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = StationIndex(list(FuelStation.objects.all()))
    return _index


def reset_index():
    """Drop the in-memory copy (tests, or after re-running load_stations)."""
    global _index
    with _lock:
        _index = None
