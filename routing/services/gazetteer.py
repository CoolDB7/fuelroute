"""
Offline US place lookup built from the `zipcodes` package (bundled data, no
network). Used for two things:

  1. placing every fuel station in the CSV (which has city + state only), and
  2. resolving "City, ST" or ZIP inputs without calling a geocoding API.

City position = median of the centroids of that city's ZIP codes.
"""
import re
import threading

import numpy as np
import zipcodes
from scipy.spatial import cKDTree

# Rough planar-projection scale for a coarse "is this near the USA" check.
# Not a substitute for a real country polygon, but cheap and good enough to
# separate border cities (Toronto, Vancouver, Winnipeg) from genuine US towns
# near the border (Buffalo, Blaine WA, International Falls) -- see the
# gazetteer tests for the distances this was tuned against.
_MILES_PER_DEGREE_LAT = 69.0
NEAR_USA_THRESHOLD_MILES = 15.0

STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
STATE_CODES = set(STATE_NAMES.values())

_lock = threading.Lock()
_places = None  # {(normalised_city, STATE): (lat, lon)}


def normalise_city(name):
    """'St. Louis' / 'Saint Louis' / 'De Forest' / 'DeForest' -> comparable keys."""
    s = name.lower().strip()
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\bmount\b", "mt", s)
    s = re.sub(r"\bfort\b", "ft", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _build():
    primary, secondary = {}, {}
    for z in zipcodes.list_all():
        try:
            pt = (float(z["lat"]), float(z["long"]))
        except (TypeError, ValueError):
            continue
        state = z["state"]
        primary.setdefault((normalise_city(z["city"]), state), []).append(pt)
        for alt in z.get("acceptable_cities") or []:
            secondary.setdefault((normalise_city(alt), state), []).append(pt)

    def median(points):
        arr = np.array(points)
        return float(np.median(arr[:, 0])), float(np.median(arr[:, 1]))

    places = {k: median(v) for k, v in secondary.items()}
    places.update({k: median(v) for k, v in primary.items()})  # primary names win
    return places


def get_places():
    global _places
    if _places is None:
        with _lock:
            if _places is None:
                _places = _build()
    return _places


def lookup_city(city, state):
    """(lat, lon) for a US city, or None."""
    return get_places().get((normalise_city(city), state.upper()))


def lookup_zip(zip_code):
    """(lat, lon, 'City, ST') for a 5-digit ZIP, or None."""
    for z in zipcodes.matching(zip_code[:5]):
        try:
            return float(z["lat"]), float(z["long"]), f"{z['city']}, {z['state']}"
        except (TypeError, ValueError):
            continue
    return None


def warm_up_in_background():
    threading.Thread(target=get_places, daemon=True).start()


_kdtree = None


def _project(lat, lon):
    x = lon * _MILES_PER_DEGREE_LAT * np.cos(np.radians(lat))
    y = lat * _MILES_PER_DEGREE_LAT
    return x, y


def _build_kdtree():
    lats, lons = [], []
    for z in zipcodes.list_all():
        try:
            lats.append(float(z["lat"]))
            lons.append(float(z["long"]))
        except (TypeError, ValueError):
            continue
    x, y = _project(np.array(lats), np.array(lons))
    return cKDTree(np.column_stack([x, y]))


def _get_kdtree():
    global _kdtree
    if _kdtree is None:
        with _lock:
            if _kdtree is None:
                _kdtree = _build_kdtree()
    return _kdtree


def distance_to_nearest_us_zip_miles(lat, lon):
    """Straight-line miles from (lat, lon) to the closest known US ZIP centroid."""
    x, y = _project(lat, lon)
    distance, _ = _get_kdtree().query([x, y])
    return float(distance)
