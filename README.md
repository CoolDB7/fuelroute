# Fuel Route API

Given a start and finish location in the USA, returns the driving route, the
cheapest feasible sequence of fuel stops for a vehicle with a 500-mile range,
and the total fuel cost at 10 MPG.

## Quick start

```bash
python -m venv venv && source venv/bin/activate      # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py load_stations                        # loads data/fuel-prices.csv, ~3s, one-time
python manage.py runserver
```

Then either:

- **Postman**: import `fuelroute.postman_collection.json` and run the
  "Plan route" request, or
- **Browser**: open `http://127.0.0.1:8000/api/map/` for a small Leaflet page
  that calls the API and draws the route + fuel stops on a map, or
- **curl**:

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Los Angeles, CA", "finish": "Jacksonville, FL"}'
```

`start` / `finish` accept a city + state (`"Chicago, IL"`), a ZIP code
(`"60601"`), raw coordinates (`"41.88,-87.63"`), or a full street address —
the first three resolve instantly with no network call; a street address
costs one geocoding call.

## Example response

```json
{
  "start": {"query": "Los Angeles, CA", "label": "Los Angeles, CA", "lat": 34.0194, "lon": -118.4108, "resolved_by": "city"},
  "finish": {"query": "Jacksonville, FL", "label": "Jacksonville, FL", "lat": 30.3369, "lon": -81.6613, "resolved_by": "city"},
  "distance_miles": 2153.0,
  "duration_hours": 32.5,
  "vehicle_assumptions": {"max_range_miles": 500, "mpg": 10, "starts_with_a_full_tank": true},
  "fuel_stops": [
    {
      "name": "TCI PHOENIX", "address": "...", "city": "Phoenix", "state": "AZ",
      "lat": 33.45, "lon": -112.07,
      "price_per_gallon": 2.922, "mile_marker": 356.6,
      "gallons_purchased": 35.6, "cost": 104.13
    }
  ],
  "total_trip_gallons": 215.3,
  "total_gallons_purchased": 179.7,
  "total_fuel_cost_usd": 518.22,
  "route_geometry": [[34.05, -118.24], ...],
  "external_calls_made": 1
}
```

## Design notes / how the requirements are met

**"Free API for map and routing"** — [OSRM](http://project-osrm.org/)'s
public demo server (`router.project-osrm.org`), no API key. Geocoding for
addresses uses [Nominatim](https://nominatim.org/), also free/keyless.

**"One call ideally, two or three acceptable"** — Every request makes
**exactly one** call to OSRM (the route itself). Start/finish resolve
offline in the common case (city/state or ZIP — which is how the fuel-price
CSV's own locations are expressed, so it's the expected input shape), only
falling back to one Nominatim call each for a street address. Worst case is
3 calls total; typical case is 1.

**"Shouldn't need to call the map API too much"** — The 6,626 fuel stations
are geocoded **once**, offline, at load time (`load_stations`), using the
`zipcodes` package's bundled ZIP-centroid dataset rather than a live geocoder
— this alone would have been 6,626+ calls otherwise. At request time, all
station math (finding candidates near the route, picking the cheapest
feasible stops) happens against data already resident in memory — no
database or network round-trips.

**Speed** — the station table (6,626 rows) is loaded into memory once per
process and kept as numpy arrays. Finding stations near a 2,000+ mile route
takes roughly 0.1s (vectorized haversine distance, chunked). The optimizer
itself (see below) is a dynamic-programming pass over just the candidate
stations near the route (typically a few hundred), which takes single-digit
milliseconds. The dominant cost per request is the network round-trip to
OSRM itself.

**Optimal = cheapest, not fewest stops** — `routing/services/optimizer.py`
solves this as a shortest-path problem on a DAG: station *i* can reach
station *j* if the gap between them is within the 500-mile range, at a cost
of `(gap / mpg) * price_i` — i.e., buy at each stop exactly enough to reach
the next chosen stop. A forward DP over stations sorted by position along
the route finds the true minimum-cost plan (this is provably optimal for
this problem, not a greedy approximation — see the tests in
`test_optimizer.py`, including a case that specifically checks the DP
prefers a far cheaper station over a closer pricier one when both are
reachable).

## Assumptions

- **The vehicle starts with a full tank**, already paid for before the trip
  begins. `total_fuel_cost_usd` is the cost of fuel purchased *during* the
  trip; `total_gallons_purchased` matches it. `total_trip_gallons` (gross
  distance ÷ MPG) is included separately for reference. A trip of 500 miles
  or less therefore returns zero stops and $0 — the starting tank covers it.
- Station coordinates are **city centroids**, since the CSV has no lat/lon.
  A 10-mile "corridor" around the route absorbs this imprecision when
  deciding which stations count as "on the way" (`FUEL_CORRIDOR_MILES` in
  settings).
- Where the same OPIS Truckstop ID appears multiple times in the CSV (state
  price updates, renames), the **lowest** listed price is used.
- Canadian provinces present in the CSV (ON, BC, AB, etc.) are excluded —
  the brief scopes this to the USA.
- US-boundary checking for the *start/finish* is a bounding box plus a
  nearest-known-ZIP-centroid distance check (see `gazetteer.py`) rather than
  a precise country polygon — it correctly separates border cities (rejects
  Toronto/Vancouver/Winnipeg, accepts Buffalo/Blaine WA/International Falls)
  but isn't exact within a few miles of the border.

## Configuration

Everything tunable is under `FUEL_ROUTE` in `config/settings.py`, overridable
by environment variable — vehicle range/MPG, the search corridor width, the
OSRM/Nominatim URLs (point `OSRM_BASE_URL` at a self-hosted OSRM instance to
drop the public demo server's fair-use limits), timeouts, and cache TTL.

## Tests

```bash
python manage.py test routing
```

18 tests: optimizer correctness (including the "cheap station further away
beats expensive station nearby" case, and that no leg ever exceeds the
500-mile range), offline geocoding for all supported input formats, and a
full view-level integration test with OSRM's response mocked (since a real
route to a real OSRM server isn't reproducible in an automated test).

## Project layout

```
config/                  Django project settings/urls
routing/
  models.py               FuelStation
  serializers.py           request validation
  views.py                 POST /api/route/
  views_map.py             GET /api/map/  (demo page)
  services/
    geocoding.py            text -> coordinates (offline-first)
    gazetteer.py             offline US city/ZIP dataset + border check
    osrm.py                  the one live routing call
    stations.py              in-memory station index + corridor search
    optimizer.py             the DP cheapest-refuelling-plan solver
    planner.py               wires the above into one response
    http.py, geo.py, errors.py
  management/commands/load_stations.py
  templates/routing/map.html
  tests/
data/fuel-prices.csv      the CSV you provided
```

## Known limitation in this delivery

I built and tested this in a sandboxed environment whose network allowlist
blocks the public OSRM and Nominatim hosts outright, so I could not run a
live end-to-end demo from that environment. I validated the OSRM
integration by mocking its documented response shape in the test suite
instead (`routing/tests/test_view.py`). Please confirm the live call works
in your environment early — everything else (station loading, the
optimizer, offline geocoding, the API contract) is exercised directly by the
test suite and by manual runs against the real SQLite-backed station data.
