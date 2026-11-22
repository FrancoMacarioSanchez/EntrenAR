"""Búsqueda difusa en el catálogo (pg_trgm) y match de lo que devuelve la IA contra alimentos reales."""
from django.contrib.postgres.search import TrigramSimilarity, TrigramWordSimilarity
from django.db.models import Q
from django.db.models.functions import Greatest

from .models import FoodItem, FoodName
from .text import compatible, normalize

# Orden de confianza de cada origen cuando dos alimentos empatan en parecido.
SOURCE_RANK = {"base": 4, "import": 4, "off": 3, "user": 2, "ia": 1}


def _rows(q, limit):
    """Coincidencias por nombre o alias: [(food_id, score, sim, texto)]. Coincidencia exacta = 1.0."""
    rows = (
        FoodName.objects.annotate(sim=TrigramSimilarity("text", q),
                                  score=Greatest(TrigramSimilarity("text", q), TrigramWordSimilarity(q, "text") * 0.95))
        .filter(Q(score__gte=0.25) | Q(text__contains=q))
        .order_by("-score")
        .values_list("food_id", "score", "sim", "text")[:limit]
    )
    return [(f, 1.0 if t == q else s, 1.0 if t == q else si, t) for f, s, si, t in rows]


def _sort_key(food, score):
    return (round(score, 2), food.verified, SOURCE_RANK.get(food.source, 0), food.times_used)


def search(query, limit=20, include_ai=True):
    """Devuelve [(FoodItem, score, texto_que_coincidió)] ordenado por relevancia (un resultado por alimento)."""
    q = normalize(query)
    if not q:
        return []
    if q.isdigit() and len(q) >= 8:
        food = FoodItem.objects.filter(barcode=q).first()
        return [(food, 1.0, q)] if food else []
    best = {}
    for food_id, score, _, text in _rows(q, limit * 4):
        if food_id not in best or score > best[food_id][0]:
            best[food_id] = (score, text)
    foods = FoodItem.objects.in_bulk(best.keys())
    out = [(foods[i], s, t) for i, (s, t) in best.items() if i in foods]
    if not include_ai:
        out = [o for o in out if o[0].source != FoodItem.Source.AI]
    out.sort(key=lambda o: _sort_key(o[0], o[1]), reverse=True)
    return out[:limit]


def best_match(term, alternatives=3):
    """El alimento del catálogo que corresponde a `term` (o None) y algunas alternativas para cambiarlo rápido.

    Se revisan todos los nombres y alias de cada candidato: alcanza con que uno sea compatible.
    """
    q = normalize(term)
    if not q:
        return None, []
    rows = _rows(q, 60)
    foods = FoodItem.objects.in_bulk({r[0] for r in rows})
    ok = {}
    ranked = {}
    for food_id, score, sim, text in rows:
        if food_id not in foods:
            continue
        ranked[food_id] = max(ranked.get(food_id, 0), score)
        if compatible(q, text, score, sim):
            ok[food_id] = max(ok.get(food_id, 0), score)
    match = None
    if ok:
        fid = max(ok, key=lambda i: _sort_key(foods[i], ok[i]))
        match = (foods[fid], ok[fid])
    alts = sorted((i for i in ranked if not match or i != match[0].pk),
                  key=lambda i: _sort_key(foods[i], ranked[i]), reverse=True)[:alternatives]
    return match, [foods[i] for i in alts]
