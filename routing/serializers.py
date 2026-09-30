from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200, help_text='e.g. "Los Angeles, CA", a ZIP code, or "lat,lon"'
    )
    finish = serializers.CharField(max_length=200, help_text="Same accepted formats as start")
