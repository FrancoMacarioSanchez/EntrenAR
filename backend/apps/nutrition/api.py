"""API de nutrición para la PWA: alumno (registro, IA, metas, estadísticas) y entrenador (seguimiento)."""
from datetime import timedelta
from functools import wraps

from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.api import data as J
from apps.api.permissions import IsStudent, IsTrainer
from apps.core.notify import notify
from apps.foods.models import FoodItem
from apps.foods.openfoodfacts import lookup as off_lookup
from apps.foods.openfoodfacts import valid_barcode
from apps.foods.search import search as food_search

from . import gemini, services, stats
from .analysis import build_draft, clean_per100, food_mini, prepare_image, totals
from .models import AIRequest, MealLog, MealLogItem, MealType, NutritionProfile, SavedMeal

MEAL_ORDER = [m for m, _ in MealType.choices]


def module_required(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        if not services.enabled(request):
            return Response({"detail": "Tu gimnasio no tiene activado el módulo de nutrición."}, status=403)
        return view(request, *args, **kwargs)
    return inner


class AIThrottle(UserRateThrottle):
    """Máximo 8 análisis por minuto por usuario (además del límite diario del plan)."""
    scope = "nutrition_ai"
    rate = "8/min"

    def get_cache_key(self, request, view):
        from django.db import connection
        key = super().get_cache_key(request, view)
        return f"{connection.schema_name}:{key}" if key else None


# ------------------------------------------------------------------ JSON

def item_json(it):
    return {"id": it.pk, "food_id": it.food_id, "name": it.name, "grams": float(it.grams), "portion": it.portion,
            "kcal": float(it.kcal), "protein": float(it.protein), "carbs": float(it.carbs), "fat": float(it.fat),
            "fiber": float(it.fiber) if it.fiber is not None else None,
            "from_ai": getattr(it, "from_ai", False)}


def meal_json(request, m):
    items = [item_json(i) for i in m.items.all()]
    return {"id": m.pk, "date": m.date, "meal_type": m.meal_type, "meal_label": m.get_meal_type_display(),
            "source": m.source, "notes": m.notes, "image": J.media(request, m.image),
            "created_at": m.created_at, "items": items, "totals": totals(items, key=None) if items else None}


def profile_json(member, profile):
    sug, data, missing = services.suggestion(member, profile)
    return {
        "goal": profile.goal, "pace": profile.pace, "activity": profile.activity,
        "weight_kg": float(profile.weight_kg) if profile.weight_kg else None,
        "targets": profile.targets, "is_custom": profile.is_custom, "trainer_notes": profile.trainer_notes,
        "updated_at": profile.updated_at,
        "updated_by": profile.updated_by.get_full_name() if profile.updated_by else None,
        "suggestion": sug, "body": data, "missing": missing,
        "choices": {
            "goal": NutritionProfile.Goal.choices, "pace": NutritionProfile.Pace.choices,
            "activity": NutritionProfile.Activity.choices,
        },
    }


def _date(request):
    return parse_date(request.GET.get("date") or "") or timezone.localdate()


# ------------------------------------------------------------------ alumno: perfil y metas

@api_view(["GET", "PUT"])
@permission_classes([IsStudent])
@module_required
def my_profile(request):
    member = request.user.member
    profile = services.get_profile(member)
    if request.method == "PUT":
        d = request.data
        for field, choices in (("goal", NutritionProfile.Goal), ("pace", NutritionProfile.Pace),
                               ("activity", NutritionProfile.Activity)):
            if d.get(field) in choices.values:
                setattr(profile, field, d[field])
        if "weight_kg" in d:
            try:
                w = float(d["weight_kg"]) if d["weight_kg"] not in (None, "") else None
            except (TypeError, ValueError):
                return Response({"detail": "Peso inválido."}, status=400)
            if w is not None and not 25 <= w <= 300:
                return Response({"detail": "El peso tiene que estar entre 25 y 300 kg."}, status=400)
            profile.weight_kg = w
        # Datos de la ficha: el alumno solo los completa si están vacíos.
        changed = []
        if d.get("height_cm") and not member.height_cm:
            try:
                h = float(d["height_cm"])
            except (TypeError, ValueError):
                return Response({"detail": "Altura inválida."}, status=400)
            if not 100 <= h <= 230:
                return Response({"detail": "La altura tiene que estar entre 100 y 230 cm."}, status=400)
            member.height_cm = h
            changed.append("height_cm")
        if d.get("birth_date") and not member.birth_date:
            bd = parse_date(str(d["birth_date"]))
            if not bd or not 10 <= (timezone.localdate() - bd).days / 365.25 <= 100:
                return Response({"detail": "Fecha de nacimiento inválida."}, status=400)
            member.birth_date = bd
            changed.append("birth_date")
        if changed:
            member.save(update_fields=changed)
        profile.save()
        services.recalc(member, profile, request.user)
    elif not profile.calories:
        services.recalc(member, profile)
    return Response(profile_json(member, profile))


# ------------------------------------------------------------------ alumno: día

@api_view(["GET"])
@permission_classes([IsStudent])
@module_required
def my_day(request):
    member = request.user.member
    day = _date(request)
    profile = services.get_profile(member)
    if not profile.calories:
        services.recalc(member, profile)
    meals = MealLog.objects.filter(member=member, date=day).prefetch_related("items")
    meals_json = [meal_json(request, m) for m in meals]
    all_items = [i for m in meals_json for i in m["items"]]
    tot = totals(all_items, key=None)
    targets = profile.targets
    groups = [{"meal_type": t, "label": label, "meals": [m for m in meals_json if m["meal_type"] == t]}
              for t, label in MealType.choices]
    for g in groups:
        its = [i for m in g["meals"] for i in m["items"]]
        g["totals"] = totals(its, key=None) if its else None
    return Response({
        "date": day, "targets": targets, "totals": tot,
        "remaining": {k: round(targets[k] - tot[k], 1) for k in targets} if targets else None,
        "groups": groups, "streak": stats.streak(member),
        "is_custom": profile.is_custom, "trainer_notes": profile.trainer_notes,
        "profile_ready": bool(targets),
        "ai": services.ai_status(request),
    })


# ------------------------------------------------------------------ alumno: análisis con IA

@api_view(["POST"])
@permission_classes([IsStudent])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([AIThrottle])
@module_required
def analyze(request):
    member = request.user.member
    status = services.ai_status(request)
    limit = status["limit"]
    if status["reason"] == "not_enabled":
        return Response({"detail": "El análisis con IA no está activado para vos en este gimnasio. "
                                   "Podés cargar la comida buscando los alimentos.", "reason": "not_enabled"}, status=403)
    if status["reason"] == "budget":
        return Response({"detail": "El análisis con IA está pausado hasta el mes que viene. "
                                   "Podés cargar la comida buscando los alimentos.", "reason": "budget"}, status=403)
    if status["reason"] == "not_configured":
        return Response({"detail": "El análisis con IA todavía no está activado en este servidor.",
                         "reason": "not_configured"}, status=503)
    if status["reason"] == "limit":
        return Response({"detail": f"Ya usaste los {limit} análisis con IA de hoy. Mañana se renuevan; mientras "
                                   "tanto podés buscar los alimentos a mano.", "reason": "limit"}, status=429)
    photo = request.FILES.get("photo")
    text = str(request.data.get("text") or "").strip()[:500]
    hint = str(request.data.get("hint") or "").strip()[:200]
    if not photo and len(text) < 3:
        return Response({"detail": "Mandá una foto o escribí qué comiste."}, status=400)

    image = None
    if photo:
        if photo.size > 10 * 1024 * 1024:
            return Response({"detail": "La foto es demasiado pesada (máx. 10 MB)."}, status=400)
        try:
            image = prepare_image(photo)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

    req = AIRequest(user=request.user, member=member, kind=AIRequest.Kind.PHOTO if image else AIRequest.Kind.TEXT,
                    input_text=text or hint)
    try:
        ai, meta = gemini.analyze(image=image, text=text, hint=hint)
    except gemini.GeminiError as e:
        req.status, req.error = AIRequest.Status.ERROR, str(e)[:300]
        req.save()
        return Response({"detail": str(e)}, status=502)

    req.model, req.result = meta["model"], ai
    from apps.tenants.ai_billing import record_usage
    record_usage(getattr(request, "tenant", None), meta["tokens_in"], meta["tokens_out"])
    req.tokens_in, req.tokens_out, req.latency_ms = meta["tokens_in"], meta["tokens_out"], meta["latency_ms"]
    if image:
        from django.core.files.base import ContentFile
        req.image.save("comida.jpg", ContentFile(image), save=False)
    items = build_draft(ai) if ai.get("is_food") else []
    if not items:
        req.status = AIRequest.Status.NOT_FOOD
    req.save()
    if not items:
        return Response({"detail": "No reconocimos comida en " + ("la foto." if image else "el texto.") +
                                   " Probá con otra foto o escribilo con más detalle.",
                         "ai_request": req.pk}, status=422)
    return Response({
        "ai_request": req.pk, "meal_name": str(ai.get("meal_name") or "")[:120],
        "notes": str(ai.get("notes") or "")[:300], "items": items, "totals": totals(items),
        "image": J.media(request, req.image), "demo": meta.get("demo", False),
        "ai": services.ai_status(request),
    })


# ------------------------------------------------------------------ alumno: comidas

@api_view(["POST"])
@permission_classes([IsStudent])
@module_required
def meals(request):
    member = request.user.member
    ai_req = None
    if request.data.get("ai_request"):
        ai_req = AIRequest.objects.filter(pk=request.data["ai_request"], user=request.user).first()
    try:
        meal = services.save_meal(member, request.data, ai_request=ai_req)
    except services.NutritionError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(meal_json(request, meal), status=201)


@api_view(["PUT", "DELETE"])
@permission_classes([IsStudent])
@module_required
def meal_detail(request, pk):
    meal = get_object_or_404(MealLog, pk=pk, member=request.user.member)
    if request.method == "DELETE":
        meal.delete()
        return Response(status=204)
    try:
        services.replace_items(meal, request.data)
    except services.NutritionError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(meal_json(request, meal))


@api_view(["POST"])
@permission_classes([IsStudent])
@module_required
def meal_habitual(request, pk):
    meal = get_object_or_404(MealLog, pk=pk, member=request.user.member)
    try:
        saved = services.save_as_habitual(request.user.member, meal, request.data.get("name"))
    except services.NutritionError as e:
        return Response({"detail": str(e)}, status=400)
    return Response({"id": saved.pk, "name": saved.name}, status=201)


@api_view(["POST"])
@permission_classes([IsStudent])
@module_required
def copy(request):
    member = request.user.member
    src = parse_date(str(request.data.get("from_date") or "")) or timezone.localdate() - timedelta(days=1)
    dst = parse_date(str(request.data.get("to_date") or "")) or timezone.localdate()
    mt = request.data.get("meal_type") if request.data.get("meal_type") in MealType.values else None
    try:
        created = services.copy_meals(member, src, dst, mt)
    except services.NutritionError as e:
        return Response({"detail": str(e)}, status=400)
    return Response({"created": len(created)}, status=201)


# ------------------------------------------------------------------ alumno: habituales y recientes

def saved_json(s):
    items = [item_json(i) for i in s.items.all()]
    return {"id": s.pk, "name": s.name, "meal_type": s.meal_type, "times_used": s.times_used,
            "items": items, "totals": totals(items, key=None)}


@api_view(["GET"])
@permission_classes([IsStudent])
@module_required
def saved_list(request):
    qs = SavedMeal.objects.filter(member=request.user.member).prefetch_related("items")
    return Response([saved_json(s) for s in qs])


@api_view(["POST", "DELETE"])
@permission_classes([IsStudent])
@module_required
def saved_detail(request, pk):
    saved = get_object_or_404(SavedMeal, pk=pk, member=request.user.member)
    if request.method == "DELETE":
        saved.delete()
        return Response(status=204)
    mt = request.data.get("meal_type") if request.data.get("meal_type") in MealType.values else None
    d = parse_date(str(request.data.get("date") or "")) or timezone.localdate()
    meal = services.log_saved(request.user.member, saved, mt, d)
    return Response(meal_json(request, meal), status=201)


@api_view(["GET"])
@permission_classes([IsStudent])
@module_required
def recent_foods(request):
    """Alimentos que más usó el alumno en los últimos 30 días (para cargar con un toque)."""
    since = timezone.localdate() - timedelta(days=30)
    rows = (MealLogItem.objects.filter(meal__member=request.user.member, meal__date__gte=since,
                                       food__isnull=False)
            .values("food_id").annotate(n=Count("id"), last=Max("meal__date"), grams=Max("grams"))
            .order_by("-n", "-last")[:20])
    foods = FoodItem.objects.in_bulk([r["food_id"] for r in rows])
    out = []
    for r in rows:
        f = foods.get(r["food_id"])
        if f:
            d = food_mini(f)
            d["last_grams"] = float(r["grams"])
            out.append(d)
    return Response(out)


# ------------------------------------------------------------------ alumno: estadísticas

@api_view(["GET"])
@permission_classes([IsStudent])
@module_required
def my_stats(request):
    member = request.user.member
    try:
        days = min(max(int(request.GET.get("days", 30)), 7), 120)
    except ValueError:
        days = 30
    profile = services.get_profile(member)
    return Response({**stats.series(member, days, profile.targets), "targets": profile.targets,
                     "streak": stats.streak(member), "adherence": stats.adherence(member, profile.targets)})


# ------------------------------------------------------------------ catálogo

@api_view(["GET"])
@module_required
def foods_search(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return Response([])
    return Response([{**food_mini(f), "score": round(s, 2)} for f, s, _ in food_search(q, limit=25)])


@api_view(["GET"])
@module_required
def foods_barcode(request, code):
    if not valid_barcode(code):
        return Response({"detail": "Código de barras inválido."}, status=400)
    food = off_lookup(code)
    if not food:
        return Response({"detail": "No encontramos ese producto. Podés cargarlo con los datos de la etiqueta.",
                         "barcode": code}, status=404)
    return Response(food_mini(food))


@api_view(["POST"])
@module_required
def foods_create(request):
    """Alimento cargado desde la etiqueta (queda sin verificar hasta que CoreX lo revise)."""
    d = request.data
    name = str(d.get("name") or "").strip()[:160]
    if len(name) < 2:
        return Response({"detail": "Falta el nombre."}, status=400)
    try:
        serving = float(d.get("serving_g")) if d.get("serving_g") else None
    except (TypeError, ValueError):
        serving = None
    # Las etiquetas argentinas traen los valores por porción: si viene la porción, se pasa a 100 g.
    per = clean_per100(d.get("per100") or {})
    if d.get("per_serving") and serving:
        per = clean_per100({k: (v or 0) * 100 / serving if v is not None else None for k, v in per.items()})
    if not per["kcal"]:
        return Response({"detail": "Faltan las calorías."}, status=400)
    barcode = valid_barcode(str(d.get("barcode") or ""))
    if barcode and FoodItem.objects.filter(barcode=barcode).exists():
        return Response(food_mini(FoodItem.objects.get(barcode=barcode)))
    from django.db import connection
    food = FoodItem.objects.create(
        name=name, brand=str(d.get("brand") or "").strip()[:80], barcode=barcode, kcal=per["kcal"],
        protein=per["protein"], carbs=per["carbs"], fat=per["fat"], fiber=per["fiber"],
        is_liquid=bool(d.get("is_liquid")), source=FoodItem.Source.USER, created_in=connection.schema_name)
    food.set_names()
    if serving:
        food.portions.create(label="porción", grams=round(serving, 1))
    return Response(food_mini(food), status=201)


# ------------------------------------------------------------------ entrenador

def _students(user):
    from apps.api.views_trainer import students_qs
    return students_qs(user)


@api_view(["GET"])
@permission_classes([IsTrainer])
@module_required
def trainer_board(request):
    """Semáforo de adherencia de los alumnos que registran comidas."""
    since = timezone.localdate() - timedelta(days=30)
    active = set(MealLog.objects.filter(date__gte=since).values_list("member_id", flat=True))
    profiles = {p.member_id: p for p in NutritionProfile.objects.filter(member_id__in=active)}
    out = []
    for m in _students(request.user).filter(pk__in=active).select_related("trainer"):
        p = profiles.get(m.pk)
        targets = p.targets if p else None
        adh = stats.adherence(m, targets)
        out.append({**J.member_json(request, m), "targets": targets, "is_custom": bool(p and p.is_custom),
                    "goal": p.get_goal_display() if p else None, "adherence": adh,
                    "streak": stats.streak(m)})
    rank = {"red": 0, "yellow": 1, "green": 2}
    out.sort(key=lambda x: (rank[x["adherence"]["color"]], x["name"]))
    return Response(out)


@api_view(["GET", "PUT"])
@permission_classes([IsTrainer])
@module_required
def trainer_student(request, pk):
    member = get_object_or_404(_students(request.user), pk=pk)
    profile = services.get_profile(member)
    if request.method == "PUT":
        d = request.data
        if d.get("reset"):
            profile.is_custom = False
        else:
            try:
                vals = {k: int(d[k]) for k in ("calories", "protein_g", "carbs_g", "fat_g")}
            except (KeyError, TypeError, ValueError):
                return Response({"detail": "Completá calorías, proteínas, carbohidratos y grasas."}, status=400)
            if not 800 <= vals["calories"] <= 7000 or any(not 0 <= vals[k] <= 1000 for k in vals if k != "calories"):
                return Response({"detail": "Revisá los valores: calorías entre 800 y 7000, macros hasta 1000 g."},
                                status=400)
            for k, v in vals.items():
                setattr(profile, k, v)
            profile.is_custom = True
        for field, choices in (("goal", NutritionProfile.Goal), ("pace", NutritionProfile.Pace),
                               ("activity", NutritionProfile.Activity)):
            if d.get(field) in choices.values:
                setattr(profile, field, d[field])
        if "trainer_notes" in d:
            profile.trainer_notes = str(d["trainer_notes"] or "")[:2000]
        profile.updated_by = request.user
        profile.save()
        if not profile.is_custom:
            services.recalc(member, profile, request.user)
        if member.user:
            notify(member.user, "Tu entrenador actualizó tu plan de nutrición",
                   f"Meta diaria: {profile.calories} kcal · {profile.protein_g} g de proteínas.",
                   url="/app/nutricion", kind="info")
    days = MealLog.objects.filter(member=member).order_by("-date").values_list("date", flat=True).distinct()[:7]
    recent = []
    for d in days:
        meals = MealLog.objects.filter(member=member, date=d).prefetch_related("items")
        mj = [meal_json(request, m) for m in meals]
        recent.append({"date": d, "meals": mj, "totals": totals([i for m in mj for i in m["items"]], key=None)})
    return Response({
        "member": J.member_json(request, member), "profile": profile_json(member, profile),
        "stats": stats.series(member, 30, profile.targets), "adherence": stats.adherence(member, profile.targets),
        "streak": stats.streak(member), "recent": recent,
    })
