"""Consulta de productos envasados por código de barras en Open Food Facts (base abierta y gratuita).

Cada producto encontrado se guarda en el catálogo propio: la próxima vez no se consulta afuera.
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, connection

from .models import FoodItem

log = logging.getLogger(__name__)
URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
FIELDS = "code,product_name,product_name_es,generic_name_es,brands,nutriments,serving_quantity,image_front_small_url"


def valid_barcode(code):
    code = (code or "").strip()
    return code if code.isdigit() and 8 <= len(code) <= 14 else None


def _num(n, *keys):
    for k in keys:
        v = n.get(k)
        if v not in (None, ""):
            try:
                return round(float(v), 1)
            except (TypeError, ValueError):
                continue
    return None


def parse_product(p):
    """dict de Open Food Facts → campos de FoodItem (o None si no trae calorías)."""
    n = p.get("nutriments") or {}
    kcal = _num(n, "energy-kcal_100g", "energy-kcal")
    if kcal is None:
        kj = _num(n, "energy-kj_100g", "energy_100g")
        kcal = round(kj / 4.184, 1) if kj is not None else None
    if kcal is None:
        return None
    name = (p.get("product_name_es") or p.get("product_name") or p.get("generic_name_es") or "").strip()
    if not name:
        return None
    brand = (p.get("brands") or "").split(",")[0].strip()[:80]
    serving = _num(p, "serving_quantity")
    return {
        "name": name[:160], "brand": brand, "kcal": kcal,
        "protein": _num(n, "proteins_100g") or 0, "carbs": _num(n, "carbohydrates_100g") or 0,
        "fat": _num(n, "fat_100g") or 0, "fiber": _num(n, "fiber_100g"),
        "image_url": (p.get("image_front_small_url") or "")[:200],
        "serving": serving if serving and 0 < serving < 2000 else None,
    }


def lookup(code):
    """FoodItem para el código (del catálogo propio o traído de Open Food Facts), o None."""
    code = valid_barcode(code)
    if not code:
        return None
    food = FoodItem.objects.filter(barcode=code).first()
    if food:
        return food
    miss_key = f"off:miss:{code}"
    if cache.get(miss_key):
        return None
    try:
        r = requests.get(URL.format(code=code), params={"fields": FIELDS}, timeout=6,
                         headers={"User-Agent": getattr(settings, "OFF_USER_AGENT", "EntrenAR/1.0")})
        data = r.json() if r.status_code == 200 else {}
    except (requests.RequestException, ValueError):
        log.warning("Open Food Facts no respondió para %s", code)
        return None  # no se cachea: puede ser un corte momentáneo
    parsed = parse_product(data.get("product") or {}) if data.get("status") == 1 else None
    if not parsed:
        cache.set(miss_key, True, 60 * 60 * 24)
        return None
    serving = parsed.pop("serving")
    try:
        food = FoodItem.objects.create(barcode=code, category=FoodItem.Category.OTHER, source=FoodItem.Source.OFF,
                                       created_in=connection.schema_name, **parsed)
    except IntegrityError:  # dos alumnos escanearon lo mismo al mismo tiempo
        return FoodItem.objects.filter(barcode=code).first()
    food.set_names()
    if serving:
        food.portions.create(label="porción", grams=serving)
    return food
