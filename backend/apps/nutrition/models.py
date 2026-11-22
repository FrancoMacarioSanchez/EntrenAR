from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.utils import TenantPath
from apps.foods.models import FoodItem
from apps.members.models import Member


class MealType(models.TextChoices):
    BREAKFAST = "desayuno", "Desayuno"
    LUNCH = "almuerzo", "Almuerzo"
    SNACK_PM = "merienda", "Merienda"
    DINNER = "cena", "Cena"
    SNACK = "colacion", "Colación"


class NutritionProfile(models.Model):
    class Goal(models.TextChoices):
        CUT = "cut", "Bajar grasa"
        MAINTAIN = "maintain", "Mantener"
        BULK = "bulk", "Ganar músculo"

    class Pace(models.TextChoices):
        SOFT = "suave", "Suave"
        MODERATE = "moderado", "Moderado"
        AGGRESSIVE = "agresivo", "Agresivo"

    class Activity(models.TextChoices):
        SEDENTARY = "sedentario", "Sedentario (trabajo sentado, poco movimiento)"
        LIGHT = "ligero", "Ligero (entrena 1–3 días)"
        MODERATE = "moderado", "Moderado (entrena 3–5 días)"
        HIGH = "alto", "Alto (entrena 6–7 días)"
        ATHLETE = "atleta", "Muy alto (doble turno o trabajo físico)"

    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name="nutrition", verbose_name="socio")
    goal = models.CharField("objetivo", max_length=10, choices=Goal.choices, default=Goal.MAINTAIN)
    pace = models.CharField("ritmo", max_length=10, choices=Pace.choices, default=Pace.MODERATE)
    activity = models.CharField("actividad", max_length=12, choices=Activity.choices, default=Activity.MODERATE)
    weight_kg = models.DecimalField("peso (kg)", max_digits=5, decimal_places=1, null=True, blank=True,
                                    help_text="Solo si no tiene mediciones: si las tiene se usa la última.")
    calories = models.PositiveIntegerField("calorías diarias", null=True, blank=True)
    protein_g = models.PositiveIntegerField("proteínas (g)", null=True, blank=True)
    carbs_g = models.PositiveIntegerField("carbohidratos (g)", null=True, blank=True)
    fat_g = models.PositiveIntegerField("grasas (g)", null=True, blank=True)
    is_custom = models.BooleanField("metas fijadas por el entrenador", default=False)
    trainer_notes = models.TextField("indicaciones del entrenador", blank=True)
    ai_daily_limit = models.PositiveSmallIntegerField(
        "análisis con IA por día (propio)", null=True, blank=True,
        help_text="Vacío = el límite del gimnasio. 0 = sin análisis con IA para este socio.")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil nutricional"
        verbose_name_plural = "perfiles nutricionales"

    def __str__(self):
        return f"Nutrición de {self.member}"

    @property
    def targets(self):
        if not self.calories:
            return None
        return {"kcal": self.calories, "protein": self.protein_g or 0, "carbs": self.carbs_g or 0,
                "fat": self.fat_g or 0}


class AIRequest(models.Model):
    class Kind(models.TextChoices):
        PHOTO = "photo", "Foto"
        TEXT = "text", "Texto / voz"

    class Status(models.TextChoices):
        OK = "ok", "Analizado"
        NOT_FOOD = "not_food", "No es comida"
        ERROR = "error", "Error"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_requests")
    member = models.ForeignKey(Member, null=True, on_delete=models.SET_NULL, related_name="ai_requests")
    kind = models.CharField(max_length=6, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OK)
    model = models.CharField(max_length=60, blank=True)
    input_text = models.TextField(blank=True)
    image = models.ImageField(upload_to=TenantPath("meals"), null=True, blank=True)
    result = models.JSONField(default=dict, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "análisis con IA"
        verbose_name_plural = "análisis con IA"


class MealLog(models.Model):
    class Source(models.TextChoices):
        PHOTO = "photo", "Foto"
        TEXT = "text", "Texto / voz"
        BARCODE = "barcode", "Código de barras"
        MANUAL = "manual", "Búsqueda"
        SAVED = "saved", "Comida habitual"
        COPY = "copy", "Copiada"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="meals", verbose_name="socio")
    date = models.DateField("fecha", default=timezone.localdate, db_index=True)
    meal_type = models.CharField("comida", max_length=10, choices=MealType.choices)
    source = models.CharField("carga", max_length=8, choices=Source.choices, default=Source.MANUAL)
    image = models.ImageField(upload_to=TenantPath("meals"), null=True, blank=True)
    notes = models.CharField("nota", max_length=250, blank=True)
    ai_request = models.ForeignKey(AIRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="meals")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("date", "created_at")
        indexes = [models.Index(fields=["member", "date"])]
        verbose_name = "comida registrada"
        verbose_name_plural = "comidas registradas"


class MealItemBase(models.Model):
    """Ítem con los macros guardados como «foto»: si después se corrige el catálogo, el historial no cambia."""

    food = models.ForeignKey(FoodItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField("alimento", max_length=160)
    grams = models.DecimalField("gramos", max_digits=7, decimal_places=1)
    portion = models.CharField("porción", max_length=60, blank=True, help_text="Ej: 2 unidades")
    kcal = models.DecimalField(max_digits=7, decimal_places=1)
    protein = models.DecimalField(max_digits=6, decimal_places=1)
    carbs = models.DecimalField(max_digits=6, decimal_places=1)
    fat = models.DecimalField(max_digits=6, decimal_places=1)
    fiber = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)

    class Meta:
        abstract = True


class MealLogItem(MealItemBase):
    meal = models.ForeignKey(MealLog, on_delete=models.CASCADE, related_name="items")
    from_ai = models.BooleanField("estimado por IA", default=False)

    class Meta:
        ordering = ("pk",)


class SavedMeal(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="saved_meals")
    name = models.CharField("nombre", max_length=80)
    meal_type = models.CharField("comida", max_length=10, choices=MealType.choices, blank=True)
    times_used = models.PositiveIntegerField(default=0)
    last_used = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-last_used", "-created_at")
        verbose_name = "comida habitual"
        verbose_name_plural = "comidas habituales"


class SavedMealItem(MealItemBase):
    saved = models.ForeignKey(SavedMeal, on_delete=models.CASCADE, related_name="items")

    class Meta:
        ordering = ("pk",)
