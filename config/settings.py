"""
Django settings for the fuel-route API.

Everything tunable lives at the bottom under "Fuel route API" and can be
overridden with environment variables, so nothing needs editing to deploy.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_float(name, default):
    return float(os.environ.get(name, default))


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me-in-production"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

# LocMemCache is per-process. That is fine for a single gunicorn worker or the
# dev server; switch to Redis/Memcached (one line) if you run several workers.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fuelroute",
    }
}

# ---------------------------------------------------------------------------
# Fuel route API
# ---------------------------------------------------------------------------
FUEL_ROUTE = {
    # Vehicle assumptions from the brief
    "MAX_RANGE_MILES": env_float("FUEL_MAX_RANGE_MILES", 500),
    "MPG": env_float("FUEL_MPG", 10),
    # Stations farther than this from the route line are ignored. Station
    # coordinates are city centroids (the CSV has no lat/lng), so this also
    # absorbs that positional error.
    "CORRIDOR_MILES": env_float("FUEL_CORRIDOR_MILES", 10),
    # Free routing + geocoding services (no API keys needed)
    "OSRM_BASE_URL": os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org"),
    "NOMINATIM_URL": os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"),
    # Nominatim's usage policy requires an identifying User-Agent
    "USER_AGENT": os.environ.get("FUEL_USER_AGENT", "fuelroute-assessment/1.0 (django)"),
    "HTTP_TIMEOUT_SECONDS": env_float("FUEL_HTTP_TIMEOUT", 8),
    "CACHE_SECONDS": int(env_float("FUEL_CACHE_SECONDS", 60 * 60 * 24)),
    # Response geometry is thinned to roughly this spacing to keep payloads small
    "RESPONSE_GEOMETRY_SPACING_MILES": env_float("FUEL_GEOMETRY_SPACING", 0.5),
}
