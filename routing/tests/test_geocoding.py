from django.test import SimpleTestCase

from routing.services import geocoding
from routing.services.errors import LocationError


class ResolveOfflineTests(SimpleTestCase):
    """These must resolve with ZERO network calls (external_calls == 0)."""

    def test_city_state(self):
        place = geocoding.resolve("Chicago, IL")
        self.assertEqual(place.source, "city")
        self.assertEqual(place.external_calls, 0)
        self.assertAlmostEqual(place.lat, 41.85, delta=0.6)
        self.assertAlmostEqual(place.lon, -87.65, delta=0.6)

    def test_zip_code(self):
        place = geocoding.resolve("60601")
        self.assertEqual(place.source, "zip")
        self.assertEqual(place.external_calls, 0)

    def test_raw_coordinates(self):
        place = geocoding.resolve("41.8781,-87.6298")
        self.assertEqual(place.source, "coordinates")
        self.assertEqual(place.external_calls, 0)

    def test_full_state_name(self):
        place = geocoding.resolve("Austin, Texas")
        self.assertEqual(place.source, "city")

    def test_coordinates_outside_usa_rejected(self):
        with self.assertRaises(LocationError):
            geocoding.resolve("48.8566,2.3522")  # Paris

    def test_coordinates_just_across_the_canadian_border_rejected(self):
        with self.assertRaises(LocationError):
            geocoding.resolve("43.6532,-79.3832")  # Toronto -- inside the crude US bbox

    def test_coordinates_of_a_us_border_town_accepted(self):
        place = geocoding.resolve("42.8864,-78.8784")  # Buffalo, NY
        self.assertEqual(place.source, "coordinates")

    def test_empty_input_rejected(self):
        with self.assertRaises(LocationError):
            geocoding.resolve("   ")
