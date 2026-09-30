from django.views.generic import TemplateView


class MapView(TemplateView):
    """
    A tiny page that POSTs to /api/route/ from the browser and draws the
    result with Leaflet. Not required by the API, but useful for the Loom demo
    and for sanity-checking a route visually.
    """

    template_name = "routing/map.html"
