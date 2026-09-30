from django.db import models


class FuelStation(models.Model):
    """One truck stop, with its best (lowest) retail diesel price from the CSV."""

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.PositiveIntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=6, help_text="USD per gallon")
    # The CSV has no coordinates: these are the centroid of the station's city.
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ["opis_id"]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price:.3f}"
