"""
Load data/fuel-prices.csv into the FuelStation table.

Each row in the CSV is geocoded to a lat/lon via the offline gazetteer
(city + state -> city-centroid coordinates). No network calls are made.

Usage:
    python manage.py load_stations
    python manage.py load_stations --csv path/to/other.csv
"""
import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routing.models import FuelStation
from routing.services import gazetteer

DEFAULT_CSV = Path(settings.BASE_DIR) / "data" / "fuel-prices.csv"

# Non-US postal jurisdictions that appear in the source file (Canadian
# provinces/territories). These stations are skipped: the brief scopes the
# tool to the USA, and the gazetteer has no coordinates for them anyway.
NON_US_STATES = {"AB", "BC", "MB", "NB", "NS", "ON", "QC", "SK", "YT", "NT", "NU", "PE"}


class Command(BaseCommand):
    help = "Load fuel station prices from CSV into the database, geocoding each by city/state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv", dest="csv_path", default=str(DEFAULT_CSV), help="Path to the fuel prices CSV."
        )
        parser.add_argument(
            "--clear", action="store_true", help="Delete existing FuelStation rows first."
        )

    def handle(self, *args, csv_path, clear, **options):
        path = Path(csv_path)
        if not path.exists():
            raise CommandError(f"CSV not found: {path}")

        # OPIS Truckstop ID repeats when OPIS logged several price updates or
        # renamed the same physical stop; keep only the cheapest price seen
        # per ID, since that's the number a route-optimizer should offer.
        best = {}
        skipped_non_us = 0
        skipped_ungeocoded = set()

        with path.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                opis_id = int(row["OPIS Truckstop ID"])
                state = row["State"].strip().upper()
                if state in NON_US_STATES:
                    skipped_non_us += 1
                    continue

                price = float(row["Retail Price"])
                existing = best.get(opis_id)
                if existing is None or price < existing["price"]:
                    best[opis_id] = {
                        "opis_id": opis_id,
                        "name": row["Truckstop Name"].strip(),
                        "address": row["Address"].strip(),
                        "city": row["City"].strip(),
                        "state": state,
                        "rack_id": int(row["Rack ID"]) if row["Rack ID"].strip() else None,
                        "price": price,
                    }

        objs = []
        for rec in best.values():
            hit = gazetteer.lookup_city(rec["city"], rec["state"])
            if not hit:
                skipped_ungeocoded.add((rec["city"], rec["state"]))
                continue
            objs.append(
                FuelStation(
                    opis_id=rec["opis_id"],
                    name=rec["name"],
                    address=rec["address"],
                    city=rec["city"],
                    state=rec["state"],
                    rack_id=rec["rack_id"],
                    price=rec["price"],
                    latitude=hit[0],
                    longitude=hit[1],
                )
            )

        with transaction.atomic():
            if clear:
                FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(objs, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(objs)} US stations."))
        if skipped_non_us:
            self.stdout.write(f"Skipped {skipped_non_us} non-US rows (Canadian provinces).")
        if skipped_ungeocoded:
            self.stdout.write(
                self.style.WARNING(
                    f"Could not geocode {len(skipped_ungeocoded)} city/state pairs, "
                    f"skipped: {sorted(skipped_ungeocoded)[:20]}"
                )
            )
