"""Reglas del módulo: metas, límites de IA, guardado de comidas, habituales y copias."""
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.body.models import BodyMeasurement
from apps.foods.models import FoodItem
from apps.foods.text import normalize

from . import goals
from .analysis import clean_per100, scale
from .models import AIRequest, MealLog, MealLogItem, MealType, NutritionProfile, SavedMeal, SavedMealItem


class NutritionError(Exception):
    pass


# ------------------------------------------------------------------ plan del gimnasio

def _plan(request):
    return getattr(getattr(request, "tenant", None), "plan", None)


def enabled(request):
    plan = _plan(request)
    return plan.has("nutrition") if plan else True


def _gym(request):
    gym = getattr(request, "tenant", None)
    return gym if getattr(gym, "pk", None) else None


def ai_addon(request):
    from apps.tenants.models import AIAddon
    return AIAddon.for_gym(_gym(request))


def ai_daily_limit(request, member=None, addon=None):
    """Análisis por día para este alumno: su límite propio si tiene uno, si no el del gimnasio (siempre ≤ tope de CoreX)."""
    addon = addon or ai_addon(request)
    if not addon or not addon.enabled:
        return 0
    member = member or getattr(request.user, "member", None)
    own = NutritionProfile.objects.filter(member=member).values_list("ai_daily_limit", flat=True).first() if member else None
    limit = addon.effective_daily_limit if own is None else own
    return max(0, min(limit, addon.max_daily_limit))


def ai_status(request):
    """Estado del análisis con IA para el alumno, con el motivo si no está disponible.

    reason: None (disponible) · "not_enabled" (el gimnasio no tiene el plug-in, o este alumno no tiene análisis)
    · "not_configured" (falta la clave de Gemini) · "budget" (el gimnasio llegó a su tope mensual)
    · "limit" (ya usó los de hoy).
    """
    from apps.tenants.ai_billing import budget_reached

    from . import gemini
    addon = ai_addon(request)
    limit = ai_daily_limit(request, addon=addon)
    used = ai_used_today(request.user)
    configured = gemini.is_configured() or settings.DEBUG
    if not addon or not addon.enabled or limit <= 0:
        reason = "not_enabled"
    elif not configured:
        reason = "not_configured"
    elif budget_reached(addon):
        reason = "budget"
    elif used >= limit:
        reason = "limit"
    else:
        reason = None
    return {"limit": limit, "used": used, "configured": configured, "available": reason is None, "reason": reason}


def ai_used_today(user):
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return AIRequest.objects.filter(user=user, created_at__gte=start).exclude(status=AIRequest.Status.ERROR).count()


# ------------------------------------------------------------------ perfil y metas

def get_profile(member):
    profile, _ = NutritionProfile.objects.get_or_create(member=member)
    return profile


def body_data(member, profile):
    """Datos para calcular las metas y cuáles faltan."""
    last = member.measurements.exclude(weight_kg__isnull=True).order_by("-date", "-pk").first()
    weight = last.weight_kg if last else profile.weight_kg
    height = member.height_cm or (BodyMeasurement.objects.filter(member=member, height_cm__isnull=False)
                                  .order_by("-date").values_list("height_cm", flat=True).first())
    body_fat = (member.measurements.exclude(body_fat__isnull=True).order_by("-date", "-pk")
                .values_list("body_fat", flat=True).first())
    data = {"sex": member.sex, "age": member.age, "weight_kg": float(weight) if weight else None,
            "height_cm": float(height) if height else None, "body_fat": float(body_fat) if body_fat else None,
            "weight_from_measurement": bool(last)}
    missing = [k for k, label in (("age", "fecha de nacimiento"), ("height_cm", "altura"), ("weight_kg", "peso"))
               if not data[k]]
    return data, missing


def suggestion(member, profile):
    data, missing = body_data(member, profile)
    if missing:
        return None, data, missing
    return goals.compute(data["sex"], data["weight_kg"], data["height_cm"], data["age"], profile.activity,
                         profile.goal, profile.pace, data["body_fat"]), data, []


def recalc(member, profile, user=None):
    """Recalcula las metas automáticas (no pisa las que fijó el entrenador)."""
    if profile.is_custom:
        return profile
    sug, _, _ = suggestion(member, profile)
    if sug:
        profile.calories, profile.protein_g = sug["kcal"], sug["protein"]
        profile.carbs_g, profile.fat_g = sug["carbs"], sug["fat"]
        profile.updated_by = user
        profile.save()
    return profile


# ------------------------------------------------------------------ guardar comidas

def _resolve_item(raw, from_ai_draft=False):
    """Un ítem del cliente → (food, name, grams, per100, from_ai). Los macros de catálogo nunca vienen del cliente."""
    try:
        grams = round(float(raw.get("grams")), 1)
    except (TypeError, ValueError):
        raise NutritionError("Cada alimento necesita los gramos.")
    if not 0 < grams <= 5000:
        raise NutritionError("Los gramos tienen que estar entre 1 y 5000.")
    food = None
    if raw.get("food_id"):
        food = FoodItem.objects.filter(pk=raw["food_id"]).first()
        if not food:
            raise NutritionError("Uno de los alimentos ya no existe en el catálogo.")
        return food, str(food), grams, food.per100(), False
    name = str(raw.get("name") or "").strip()[:160]
    if not name or not isinstance(raw.get("per100"), dict):
        raise NutritionError("Falta el nombre o los valores nutricionales de un alimento.")
    per100 = clean_per100(raw["per100"])
    return None, name, grams, per100, from_ai_draft or bool(raw.get("from_ai"))


def _catalog_from_ai(name, per100, source):
    """Guarda en el catálogo un alimento que no existía (queda sin verificar para que CoreX lo revise)."""
    norm = normalize(name)
    existing = FoodItem.objects.filter(names__text=norm, source__in=[FoodItem.Source.AI, FoodItem.Source.USER]).first()
    if existing:
        return existing
    food = FoodItem.objects.create(
        name=name, kcal=per100["kcal"], protein=per100["protein"], carbs=per100["carbs"], fat=per100["fat"],
        fiber=per100["fiber"], source=source, verified=False, created_in=connection.schema_name)
    food.set_names()
    return food


def _learn_alias(food, ai_term):
    """Si el alumno cambió el alimento que propuso la IA, el término de la IA pasa a ser alias del elegido."""
    term = normalize(ai_term)
    if food and len(term) >= 3:
        food.set_names([term], learned=True)


@transaction.atomic
def save_meal(member, data, ai_request=None):
    meal_type = data.get("meal_type")
    if meal_type not in MealType.values:
        raise NutritionError("Elegí a qué comida corresponde.")
    items = data.get("items") or []
    if not items or len(items) > 30:
        raise NutritionError("La comida tiene que tener entre 1 y 30 alimentos.")
    date = data.get("date") or timezone.localdate()
    if isinstance(date, str):
        from django.utils.dateparse import parse_date
        date = parse_date(date) or timezone.localdate()
    if date > timezone.localdate() + timedelta(days=1):
        raise NutritionError("No se pueden cargar comidas de días futuros.")

    source = data.get("source") if data.get("source") in MealLog.Source.values else MealLog.Source.MANUAL
    meal = MealLog.objects.create(member=member, date=date, meal_type=meal_type, source=source,
                                  notes=str(data.get("notes") or "")[:250], ai_request=ai_request)
    if ai_request and ai_request.image:
        meal.image.name = ai_request.image.name
        meal.save(update_fields=["image"])
    _write_items(meal, items, MealLogItem, from_ai_draft=bool(ai_request))
    return meal


def _write_items(parent, items, model, from_ai_draft=False):
    used = []
    for raw in items:
        food, name, grams, per100, from_ai = _resolve_item(raw, from_ai_draft and not raw.get("food_id"))
        if food is None and model is MealLogItem:
            food = _catalog_from_ai(name, per100, FoodItem.Source.AI if from_ai else FoodItem.Source.USER)
        elif food is not None and raw.get("changed") and raw.get("ai_term"):
            _learn_alias(food, raw["ai_term"])
        m = scale(per100, grams)
        kwargs = {"meal": parent} if model is MealLogItem else {"saved": parent}
        if model is MealLogItem:
            kwargs["from_ai"] = from_ai
        model.objects.create(food=food, name=name, grams=grams, portion=str(raw.get("portion") or "")[:60],
                             kcal=m["kcal"], protein=m["protein"], carbs=m["carbs"], fat=m["fat"],
                             fiber=m["fiber"], **kwargs)
        if food:
            used.append(food.pk)
    if used:
        FoodItem.objects.filter(pk__in=used).update(times_used=F("times_used") + 1)


@transaction.atomic
def replace_items(meal, data):
    items = data.get("items")
    if items is not None:
        if not items or len(items) > 30:
            raise NutritionError("La comida tiene que tener entre 1 y 30 alimentos.")
        meal.items.all().delete()
        _write_items(meal, items, MealLogItem)
    if data.get("meal_type") in MealType.values:
        meal.meal_type = data["meal_type"]
    if "notes" in data:
        meal.notes = str(data.get("notes") or "")[:250]
    meal.save()
    return meal


def _copy_items(src_items, dest, model):
    for it in src_items:
        kwargs = {"meal": dest} if model is MealLogItem else {"saved": dest}
        if model is MealLogItem:
            kwargs["from_ai"] = getattr(it, "from_ai", False)
        model.objects.create(food=it.food, name=it.name, grams=it.grams, portion=it.portion, kcal=it.kcal,
                             protein=it.protein, carbs=it.carbs, fat=it.fat, fiber=it.fiber, **kwargs)


@transaction.atomic
def save_as_habitual(member, meal, name):
    name = (name or "").strip()[:80]
    if not name:
        raise NutritionError("Ponele un nombre a la comida habitual.")
    saved = SavedMeal.objects.create(member=member, name=name, meal_type=meal.meal_type)
    _copy_items(meal.items.select_related("food"), saved, SavedMealItem)
    return saved


@transaction.atomic
def log_saved(member, saved, meal_type, date=None):
    meal = MealLog.objects.create(member=member, date=date or timezone.localdate(),
                                  meal_type=meal_type or saved.meal_type or MealType.SNACK,
                                  source=MealLog.Source.SAVED, notes=saved.name)
    _copy_items(saved.items.select_related("food"), meal, MealLogItem)
    SavedMeal.objects.filter(pk=saved.pk).update(times_used=F("times_used") + 1, last_used=timezone.now())
    return meal


@transaction.atomic
def copy_meals(member, from_date, to_date, meal_type=None):
    """«Copiar el desayuno de ayer»: duplica las comidas de un día (o de un tipo) en otra fecha."""
    qs = MealLog.objects.filter(member=member, date=from_date).prefetch_related("items__food")
    if meal_type:
        qs = qs.filter(meal_type=meal_type)
    created = []
    for src in qs:
        meal = MealLog.objects.create(member=member, date=to_date, meal_type=src.meal_type,
                                      source=MealLog.Source.COPY, notes=src.notes)
        _copy_items(src.items.all(), meal, MealLogItem)
        created.append(meal)
    if not created:
        raise NutritionError("No hay comidas para copiar en ese día.")
    return created
