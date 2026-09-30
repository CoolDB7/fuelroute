from django.test import SimpleTestCase

from routing.services.errors import NoFeasiblePlanError
from routing.services.optimizer import plan_refuelling
from routing.services.stations import Candidate


def cand(idx, mile, price):
    return Candidate(station_idx=idx, mile=mile, offset_miles=0.0, price=price)


class PlanRefuellingTests(SimpleTestCase):
    def test_trip_within_range_needs_no_stops(self):
        stops, cost = plan_refuelling(400, [cand(0, 200, 2.50)], max_range=500, mpg=10)
        self.assertEqual(stops, [])
        self.assertEqual(cost, 0.0)

    def test_picks_the_cheaper_of_two_reachable_stations(self):
        # Both stations are within range of the start; the DP should prefer
        # buying nothing at the pricier one and everything at the cheaper one,
        # if the cheaper one alone can cover the rest of the trip.
        candidates = [cand(0, 100, 5.00), cand(1, 450, 2.00)]
        stops, cost = plan_refuelling(900, candidates, max_range=500, mpg=10)
        self.assertEqual([s.station_idx for s in stops], [1])
        # 900 - 450 = 450 miles left after the cheap stop -> 45 gal @ $2.00
        self.assertAlmostEqual(cost, 45 * 2.00, places=2)

    def test_buys_minimum_needed_when_next_station_is_cheaper(self):
        # Station 1 (mile 550) is NOT reachable directly from the start
        # (550 > 500), so station 0 (mile 50, expensive) must be used first.
        # Optimal: buy just enough at 0 to reach 1, then fill cheaply at 1.
        candidates = [cand(0, 50, 4.00), cand(1, 550, 2.00)]
        stops, cost = plan_refuelling(950, candidates, max_range=500, mpg=10)
        self.assertEqual([s.station_idx for s in stops], [0, 1])
        leg0 = (550 - 50) / 10 * 4.00
        leg1 = (950 - 550) / 10 * 2.00
        self.assertAlmostEqual(cost, leg0 + leg1, places=2)

    def test_infeasible_gap_raises(self):
        candidates = [cand(0, 100, 3.00), cand(1, 900, 3.00)]  # 800mi gap > range
        with self.assertRaises(NoFeasiblePlanError):
            plan_refuelling(1000, candidates, max_range=500, mpg=10)

    def test_no_candidates_and_long_trip_raises(self):
        with self.assertRaises(NoFeasiblePlanError):
            plan_refuelling(1000, [], max_range=500, mpg=10)

    def test_never_exceeds_max_range_between_consecutive_stops(self):
        candidates = [cand(i, mile, 3.0 - (i % 3) * 0.1) for i, mile in enumerate(range(0, 2000, 80))]
        stops, _ = plan_refuelling(2000, candidates, max_range=500, mpg=10)
        miles = [0.0] + [s.mile for s in stops] + [2000.0]
        for a, b in zip(miles, miles[1:]):
            self.assertLessEqual(b - a, 500 + 1e-6)
