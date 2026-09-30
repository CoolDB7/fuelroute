class FuelRouteError(Exception):
    """Base class. `status` is the HTTP status the API should answer with."""

    status = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class LocationError(FuelRouteError):
    """The start/finish text could not be understood or is not in the USA."""

    status = 400


class NoRouteError(FuelRouteError):
    """The routing service could not connect the two points by road."""

    status = 422


class NoFeasiblePlanError(FuelRouteError):
    """A route exists, but stations along it are too far apart for a 500 mile range."""

    status = 422


class UpstreamError(FuelRouteError):
    """The free routing/geocoding service failed or timed out."""

    status = 502
