"""
Turn the `start` / `finish` text into coordinates, cheapest option first:

  1. "lat,lng"            -> parsed, 0 network calls
  2. 5-digit ZIP          -> offline lookup, 0 calls
  3. "City, ST" / "City, State name" -> offline lookup, 0 calls
  4. anything else (street addresses, landmarks) -> one Nominatim call

That keeps the common case at exactly ONE external call per request (the route
itself), and the worst case at three (two geocodes + the route).
"""
import re
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from . import gazetteer
from .errors import LocationError, UpstreamError
from .geo import in_usa
from .http import session

_LATLNG = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_ZIP = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")
_USA_SUFFIX = re.compile(r",?\s*(usa|us|united states(?: of america)?)\s*$", re.I)


@dataclass
class Place:
    query: str
    lat: float
    lon: float
    label: str
    source: str  # "coordinates" | "zip" | "city" | "nominatim"
    external_calls: int = 0

    def as_dict(self):
        return {
            "query": self.query,
            "label": self.label,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "resolved_by": self.source,
        }


def resolve(text):
    text = (text or "").strip()
    if not text:
        raise LocationError("Location is empty.")

    m = _LATLNG.match(text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        return _check_usa(Place(text, lat, lon, f"{lat:.4f}, {lon:.4f}", "coordinates"))

    m = _ZIP.match(text)
    if m:
        hit = gazetteer.lookup_zip(m.group(1))
        if not hit:
            raise LocationError(f"Unknown ZIP code '{m.group(1)}'.")
        return _check_usa(Place(text, hit[0], hit[1], f"{hit[2]} {m.group(1)}", "zip"))

    local = _try_city_state(text)
    if local:
        return _check_usa(local)

    return _check_usa(_nominatim(text))


def _try_city_state(text):
    parts = [p.strip() for p in _USA_SUFFIX.sub("", text).split(",")]
    if len(parts) != 2 or any(ch.isdigit() for ch in parts[0]):
        return None  # looks like a street address -> let Nominatim handle it
    city, state = parts
    code = state.upper() if state.upper() in gazetteer.STATE_CODES else gazetteer.STATE_NAMES.get(state.lower())
    if not code:
        return None
    hit = gazetteer.lookup_city(city, code)
    if not hit:
        return None
    return Place(text, hit[0], hit[1], f"{city.title()}, {code}", "city")


def _nominatim(text):
    key = "geocode:" + re.sub(r"\s+", " ", text.lower())
    cached = cache.get(key)
    if cached:
        return Place(**cached, external_calls=0)

    cfg = settings.FUEL_ROUTE
    try:
        resp = session().get(
            cfg["NOMINATIM_URL"],
            params={"q": text, "format": "jsonv2", "limit": 1, "countrycodes": "us"},
            timeout=cfg["HTTP_TIMEOUT_SECONDS"],
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as exc:  # network error, bad status, bad JSON
        raise UpstreamError(f"Geocoding service failed for '{text}': {exc}") from exc

    if not results:
        raise LocationError(f"Could not find '{text}' in the USA.")

    r = results[0]
    fields = dict(
        query=text,
        lat=float(r["lat"]),
        lon=float(r["lon"]),
        label=r.get("display_name", text),
        source="nominatim",
    )
    cache.set(key, fields, 60 * 60 * 24 * 30)
    return Place(**fields, external_calls=1)


def _check_usa(place):
    # Bounding box first (cheap, catches anything far from the US outright);
    # then a nearest-known-ZIP distance check to catch places that fall
    # inside the box but are actually just across the Canadian border
    # (Toronto, Vancouver, Winnipeg) while still accepting genuine US border
    # towns (Buffalo, Blaine WA, International Falls MN).
    if not in_usa(place.lat, place.lon):
        raise LocationError(f"'{place.query}' is outside the USA.")
    if gazetteer.distance_to_nearest_us_zip_miles(place.lat, place.lon) > gazetteer.NEAR_USA_THRESHOLD_MILES:
        raise LocationError(f"'{place.query}' is outside the USA.")
    return place
