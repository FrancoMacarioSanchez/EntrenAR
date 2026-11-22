"""Importa alimentos desde un CSV (por ejemplo una tabla oficial exportada a planilla).

Columnas (encabezados en la primera fila): nombre, kcal, proteinas, carbohidratos, grasas
Opcionales: fibra, marca, codigo_barras, categoria, alias ("a|b|c"), porciones ("unidad:50|taza:160"), bebida (si/no), ref

    python manage.py import_foods_csv tabla.csv --source import --verified --ref-prefix argenfoods
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.foods.models import FoodItem
from apps.foods.text import normalize

TRUE = {"1", "si", "true", "x", "yes"}


def num(v, default=None):
    v = (v or "").strip().replace(",", ".")
    try:
        return round(float(v), 1) if v else default
    except ValueError:
        return default


class Command(BaseCommand):
    help = "Importa o actualiza alimentos desde un CSV (valores por 100 g)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--source", default="import", choices=[s for s, _ in FoodItem.Source.choices])
        parser.add_argument("--verified", action="store_true")
        parser.add_argument("--ref-prefix", default="csv")
        parser.add_argument("--delimiter", default=",")

    @transaction.atomic
    def handle(self, path, source, verified, ref_prefix, delimiter, **opts):
        cats = {c for c, _ in FoodItem.Category.choices}
        created = updated = skipped = 0
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh, delimiter=delimiter))
        if not rows or "nombre" not in rows[0] or "kcal" not in rows[0]:
            raise CommandError("El CSV necesita al menos las columnas nombre y kcal.")
        for row in rows:
            name, kcal = (row.get("nombre") or "").strip(), num(row.get("kcal"))
            if not name or kcal is None:
                skipped += 1
                continue
            barcode = (row.get("codigo_barras") or "").strip() or None
            ref = (row.get("ref") or "").strip() or f"{ref_prefix}:{normalize(name).replace(' ', '-')[:60]}"
            cat = (row.get("categoria") or "").strip().lower()
            food, new = FoodItem.objects.update_or_create(ref=ref, defaults={
                "name": name[:160], "brand": (row.get("marca") or "").strip()[:80], "barcode": barcode,
                "category": cat if cat in cats else FoodItem.Category.OTHER, "kcal": kcal,
                "protein": num(row.get("proteinas"), 0), "carbs": num(row.get("carbohidratos"), 0),
                "fat": num(row.get("grasas"), 0), "fiber": num(row.get("fibra")),
                "is_liquid": (row.get("bebida") or "").strip().lower() in TRUE, "source": source,
                "verified": verified,
            })
            created += new
            updated += not new
            food.set_names([a for a in (row.get("alias") or "").split("|") if a.strip()])
            for part in filter(None, (row.get("porciones") or "").split("|")):
                if ":" in part:
                    label, grams = part.rsplit(":", 1)
                    if num(grams):
                        food.portions.update_or_create(label=label.strip()[:40], defaults={"grams": num(grams)})
        self.stdout.write(self.style.SUCCESS(f"{created} nuevos, {updated} actualizados, {skipped} filas salteadas."))
