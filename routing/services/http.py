import requests
from django.conf import settings

_session = None


def session():
    """One shared Session -> TCP/TLS connections are reused between requests."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = settings.FUEL_ROUTE["USER_AGENT"]
    return _session
