from unittest.mock import patch

import numpy as np
from django.conf import settings as dj_settings
from django.test import TestCase, override_settings

from routing.services import stations as stations_service
from routing.services.geo import haversine_miles
from routing.services.osrm import Route
from routing.models import FuelStation

_WIDE_CORRIDOR = {**dj_settings.FUEL_ROUTE, "CORRIDOR_MILES": 60}


def fake_route(start, finish):
    """A straight-line 'route' between the two geocoded points, standing in
    for a real OSRM response so tests don't need network access."""
    n = 200
    lats = np.linspace(start.lat, finish.lat, n)
    lons = np.linspace(start.lon, finish.lon, n)
    dist = float(np.sum(haversine_miles(lats[:-1], lons[:-1], lats[1:], lons[1:])))
    return Route(lats=lats, lons=lons, distance_miles=dist, duration_seconds=dist / 60 * 3600)


class RouteViewTests(TestCase):
    """
    Note on fixtures: the real ~6,600-station table is loaded into the dev
    DB by `load_stations`, not into Django's throwaway test database, so
    these tests seed their own small set of stations along a straight LA ->
    Jacksonville line and reset the process-wide station index afterwards.
    """

    @classmethod
    def setUpTestData(cls):
        lat1, lon1 = 34.0522, -118.2437  # LA
        lat2, lon2 = 30.3322, -81.6557  # Jacksonville
        FuelStation.objects.bulk_create(
            [
                FuelStation(
                    opis_id=1000 + i,
                    name=f"Test Stop {i}",
                    address="I-Test",
                    city="Testville",
                    state="TX",
                    price=2.50 + (i % 5) * 0.15,
                    latitude=lat1 + (lat2 - lat1) * frac,
                    longitude=lon1 + (lon2 - lon1) * frac,
                )
                for i, frac in enumerate(np.linspace(0.05, 0.95, 25))
            ]
        )

    def setUp(self):
        stations_service.reset_index()  # pick up setUpTestData's rows

    def tearDown(self):
        stations_service.reset_index()  # don't leak test stations into other tests

    @patch("routing.services.planner.osrm.fetch_route", side_effect=fake_route)
    @override_settings(FUEL_ROUTE=_WIDE_CORRIDOR)
    def test_long_trip_returns_fuel_stops_and_cost(self, mock_fetch):
        resp = self.client.post(
            "/api/route/", {"start": "Los Angeles, CA", "finish": "Jacksonville, FL"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(mock_fetch.call_count, 1)  # exactly one routing call
        self.assertGreater(data["distance_miles"], 2000)
        self.assertGreater(len(data["fuel_stops"]), 0)
        self.assertGreater(data["total_fuel_cost_usd"], 0)
        self.assertLessEqual(data["external_calls_made"], 1)  # both endpoints geocode offline
        # every consecutive gap (start -> stop1 -> ... -> finish) must be <= 500mi
        miles = [0.0] + [s["mile_marker"] for s in data["fuel_stops"]] + [data["distance_miles"]]
        for a, b in zip(miles, miles[1:]):
            self.assertLessEqual(b - a, 500.5)

    @patch("routing.services.planner.osrm.fetch_route", side_effect=fake_route)
    def test_short_trip_needs_no_fuel_stops(self, mock_fetch):
        resp = self.client.post(
            "/api/route/", {"start": "Los Angeles, CA", "finish": "San Diego, CA"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["fuel_stops"], [])
        self.assertEqual(data["total_fuel_cost_usd"], 0)

    def test_missing_start_is_400(self):
        resp = self.client.post("/api/route/", {"finish": "Denver, CO"}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_non_usa_location_is_400(self):
        # Raw coordinates hit the offline coordinate path (no network call),
        # so this test doesn't depend on Nominatim being reachable, and still
        # exercises the same in_usa() rejection a free-text non-US place
        # would hit after geocoding.
        resp = self.client.post(
            "/api/route/", {"start": "43.6532,-79.3832", "finish": "Denver, CO"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
