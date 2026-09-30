from django.urls import path

from . import views
from .views_map import MapView

urlpatterns = [
    path("route/", views.RouteView.as_view(), name="route"),
    path("map/", MapView.as_view(), name="map"),
]
