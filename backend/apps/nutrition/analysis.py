"""De la respuesta de la IA a un borrador editable: cada ítem se busca en el catálogo propio."""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from apps.foods.search import best_match

MAX_SIDE = 1024
LIMITS = {"kcal": 900, "protein": 100, "carbs": 100, "fat": 100, "fiber": 60}


def prepare_image(fileobj):
    """Normaliza la foto: orientación, RGB, máx. 1024 px, JPEG. Devuelve bytes (o ValueError)."""
    try:
        img = Image.open(fileobj)
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("El archivo no es una imagen válida.") from e
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue()


def _f(v, hi, default=0.0):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return round(min(max(v, 0.0), hi), 1)


def clean_per100(d):
    """Valores por 100 g saneados (lo que venga de la IA o del cliente)."""
    out = {k: _f(d.get(k), hi) for k, hi in LIMITS.items()}
    if d.get("fiber") is None:
        out["fiber"] = None
    # Si las kcal no cierran con los macros, se recalculan (protege contra errores groseros).
    est = out["protein"] * 4 + out["carbs"] * 4 + out["fat"] * 9
    if est and (out["kcal"] == 0 or abs(out["kcal"] - est) / est > 0.5):
        out["kcal"] = round(min(est, 900), 1)
    return out


def scale(per100, grams):
    g = float(grams) / 100
    return {k: (round(v * g, 1) if v is not None else None) for k, v in per100.items()}


def food_mini(food):
    return {"id": food.pk, "name": str(food), "per100": food.per100(), "verified": food.verified,
            "source": food.source, "is_liquid": food.is_liquid,
            "portions": [{"label": p.label, "grams": float(p.grams)} for p in food.portions.all()]}


def build_draft(ai):
    """Respuesta de Gemini → lista de ítems con macros (del catálogo si hay coincidencia, si no de la IA)."""
    items = []
    for it in (ai.get("items") or [])[:15]:
        name = str(it.get("name") or "").strip()[:160]
        term = str(it.get("search_term") or name).strip()[:160]
        if not name:
            continue
        grams = _f(it.get("grams"), 5000)
        if grams <= 0:
            continue
        match, alts = best_match(term)
        ai_per100 = clean_per100({"kcal": it.get("kcal_100g"), "protein": it.get("protein_100g"),
                                  "carbs": it.get("carbs_100g"), "fat": it.get("fat_100g"),
                                  "fiber": it.get("fiber_100g")})
        if match:
            food = match[0]
            per100, source, shown = food.per100(), "catalogo", str(food)
        else:
            food, per100, source, shown = None, ai_per100, "ia", name
        qty, unit = it.get("quantity"), str(it.get("unit") or "").strip()[:20]
        portion = ""
        if qty and unit and unit not in ("g", "ml", "gramos"):
            portion = f"{qty:g} {unit}" if isinstance(qty, (int, float)) else f"{qty} {unit}"
        items.append({
            "name": shown,
            "ai_name": name,
            "ai_term": term,
            "food_id": food.pk if food else None,
            "food": food_mini(food) if food else None,
            "grams": grams,
            "portion": portion[:60],
            "per100": per100,
            "ai_per100": ai_per100,
            "macros": scale(per100, grams),
            "source": source,
            "confidence": it.get("confidence") if it.get("confidence") in ("alta", "media", "baja") else "media",
            "alternatives": [food_mini(a) for a in alts],
        })
    return items


def totals(items, key="macros"):
    out = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "fiber": 0.0}
    for it in items:
        m = it[key] if key else it
        for k in out:
            out[k] += float(m.get(k) or 0)
    return {k: round(v, 1) for k, v in out.items()}
