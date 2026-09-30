"""
Cheapest feasible refuelling plan along a route.

Model
-----
The vehicle starts at mile 0 with a full tank (free — already fuelled before
the trip) giving it `max_range` miles before it must refuel. Every candidate
station near the route can sell any amount of fuel. We need a sequence of
stops, each reachable from the previous one (or from the start) within
`max_range` miles, that gets the vehicle to the finish, at minimum total cost.

This reduces to a shortest-path problem on a DAG: node i can reach node j
(mile_j > mile_i) iff (mile_j - mile_i) <= max_range, at a cost of
(mile_j - mile_i) / mpg * price_i — i.e. at each stop you buy exactly enough
fuel to reach the next chosen stop, never more. That "buy just enough" rule is
optimal here: overbuying at a station only makes sense if every reachable
station is *more* expensive, in which case the DP already prefers routing
around it via a cheaper station further on.

Candidates are sorted by mile, so a single forward pass (O(n^2) over the
stations actually near the route, typically a few hundred) computes it — no
external calls, this is pure arithmetic over data already in memory.
"""
import math
from dataclasses import dataclass

from .errors import NoFeasiblePlanError


@dataclass
class PlannedStop:
    station_idx: int
    mile: float
    price: float
    gallons_purchased: float
    cost: float


def plan_refuelling(distance_miles, candidates, max_range, mpg):
    """
    `candidates`: list of stations.Candidate (already deduped/near the route),
    in any order. Returns (stops: list[PlannedStop], total_cost: float).
    Raises NoFeasiblePlanError if no sequence of stops can cover the route.
    """
    if distance_miles <= max_range:
        return [], 0.0  # the free starting tank covers the whole trip

    # Nodes: virtual start (mile 0, free), every candidate, virtual finish.
    # A station can legitimately appear more than once along a route that
    # crosses near it twice; keep candidates as given, just sorted by mile.
    ordered = sorted(candidates, key=lambda c: c.mile)
    miles = [0.0] + [c.mile for c in ordered] + [distance_miles]
    prices = [0.0] + [c.price for c in ordered] + [0.0]
    n = len(miles)

    INF = math.inf
    dp = [INF] * n
    parent = [-1] * n
    dp[0] = 0.0

    for i in range(n - 1):
        if dp[i] == INF:
            continue
        base = miles[i]
        for j in range(i + 1, n):
            gap = miles[j] - base
            if gap > max_range + 1e-6:
                break  # sorted ascending -> nothing further is reachable either
            cost = dp[i] if j == i else dp[i] + gap / mpg * prices[i]
            if cost < dp[j]:
                dp[j] = cost
                parent[j] = i

    if dp[n - 1] == INF:
        gap = _largest_unreachable_gap(miles, max_range)
        raise NoFeasiblePlanError(
            "No sequence of fuel stops within the vehicle's 500-mile range "
            f"connects the start to the finish (a {gap:.0f}-mile gap between "
            "stations exceeds the range)."
        )

    # Reconstruct: walk parents back from the finish node.
    path = []
    node = n - 1
    while parent[node] != -1:
        path.append(node)
        node = parent[node]
    path.reverse()  # start -> ... -> finish, excluding the virtual start

    stops = []
    prev_mile = 0.0
    for node in path:
        if node == n - 1:
            break  # virtual finish is not a stop
        candidate = ordered[node - 1]
        leg = miles[node] - prev_mile
        # gallons bought here = however far the *next* chosen node is
        prev_mile = miles[node]
        stops.append(candidate)

    # Second pass to compute gallons/cost per stop now that we know the order,
    # since each stop's purchase size depends on the *next* stop's mile.
    stop_miles = [s.mile for s in stops] + [distance_miles]
    planned = []
    total_cost = 0.0
    for k, cand in enumerate(stops):
        gallons = (stop_miles[k + 1] - stop_miles[k]) / mpg
        cost = gallons * cand.price
        total_cost += cost
        planned.append(
            PlannedStop(
                station_idx=cand.station_idx,
                mile=cand.mile,
                price=cand.price,
                gallons_purchased=gallons,
                cost=cost,
            )
        )
    return planned, total_cost


def _largest_unreachable_gap(miles, max_range):
    """For a friendlier error message: the widest gap between consecutive
    candidate positions (a rough diagnostic, not part of the DP itself)."""
    gaps = [b - a for a, b in zip(miles, miles[1:])]
    return max(gaps) if gaps else 0.0
