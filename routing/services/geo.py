"""Small geographic helpers. Everything is vectorised with numpy for speed."""
import numpy as np

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344

# Generous bounding boxes: contiguous US, Alaska, Hawaii.
_US_BOXES = (
    (24.0, 49.6, -125.0, -66.5),
    (51.0, 71.6, -179.9, -129.0),
    (18.5, 22.5, -160.6, -154.5),
)


def in_usa(lat, lon):
    return any(s <= lat <= n and w <= lon <= e for s, n, w, e in _US_BOXES)


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles. Accepts scalars or broadcastable arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def cumulative_miles(lats, lons):
    """Distance from the first point to every point along a polyline."""
    steps = haversine_miles(lats[:-1], lons[:-1], lats[1:], lons[1:])
    return np.concatenate(([0.0], np.cumsum(steps)))


def thin_by_spacing(cum_miles, spacing):
    """
    Indices of points to keep so that kept points are at least `spacing` miles
    apart. The first and last points are always kept. Uses searchsorted, so it
    is O(k log n) for k kept points rather than a Python loop over every vertex.
    """
    n = len(cum_miles)
    if n <= 2:
        return np.arange(n)
    keep = [0]
    while True:
        nxt = int(np.searchsorted(cum_miles, cum_miles[keep[-1]] + spacing, side="left"))
        if nxt >= n - 1:
            break
        keep.append(nxt)
    keep.append(n - 1)
    return np.array(keep)
