from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .serializers import RouteRequestSerializer
from .services.errors import FuelRouteError
from .services.planner import plan_trip


class RouteThrottle(AnonRateThrottle):
    # Generous, but stops one client hammering the shared OSRM/Nominatim
    # public instances into rate-limiting everyone.
    rate = "60/min"


class RouteView(APIView):
    """
    POST /api/route/
    Body: {"start": "Chicago, IL", "finish": "Denver, CO"}

    Returns the driving route, the cheapest feasible sequence of fuel stops
    for a 500-mile-range vehicle at 10 MPG, and the total fuel cost.
    """

    throttle_classes = [RouteThrottle]

    def post(self, request):
        req = RouteRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        try:
            result = plan_trip(req.validated_data["start"], req.validated_data["finish"])
        except FuelRouteError as exc:
            return Response({"error": exc.message}, status=exc.status)
        return Response(result)
