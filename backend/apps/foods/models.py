"""Catálogo de alimentos compartido por todos los gimnasios (schema público).

Valores nutricionales siempre por 100 g (o 100 ml en bebidas, que se toman como gramos).
"""
from decimal import Decimal

from django.contrib.postgres.indexes import GinIndex
from django.db import models

from .text import normalize


class FoodItem(models.Model):
    class Source(models.TextChoices):
        BASE = "base", "Base CoreX"
        IMPORT = "import", "Importado (tabla oficial)"
        OFF = "off", "Open Food Facts"
        USER = "user", "Cargado por un usuario"
        AI = "ia", "Estimado por IA"

    class Category(models.TextChoices):
        CEREALS = "cereales", "Cereales, panes y pastas"
        LEGUMES = "legumbres", "Legumbres"
        TUBERS = "tuberculos", "Papa, batata y choclo"
        MEAT = "carnes", "Carnes"
        FISH = "pescados", "Pescados y mariscos"
        EGGS = "huevos", "Huevos"
        DAIRY = "lacteos", "Lácteos"
        FRUIT = "frutas", "Frutas"
        VEG = "verduras", "Verduras"
        FATS = "grasas", "Aceites y grasas"
        NUTS = "frutos_secos", "Frutos secos y semillas"
        SWEETS = "dulces", "Dulces y snacks"
        DRINKS = "bebidas", "Bebidas"
        DISHES = "platos", "Platos preparados"
        SUPPLEMENTS = "suplementos", "Suplementos"
        OTHER = "otros", "Otros"

    ref = models.CharField("referencia", max_length=80, unique=True, null=True, blank=True,
                           help_text="Identificador estable de la carga base o importada (para actualizarla).")
    name = models.CharField("nombre", max_length=160)
    brand = models.CharField("marca", max_length=80, blank=True)
    barcode = models.CharField("código de barras", max_length=32, unique=True, null=True, blank=True)
    category = models.CharField("categoría", max_length=16, choices=Category.choices, default=Category.OTHER)
    kcal = models.DecimalField("kcal / 100 g", max_digits=6, decimal_places=1)
    protein = models.DecimalField("proteínas / 100 g", max_digits=5, decimal_places=1, default=0)
    carbs = models.DecimalField("carbohidratos / 100 g", max_digits=5, decimal_places=1, default=0)
    fat = models.DecimalField("grasas / 100 g", max_digits=5, decimal_places=1, default=0)
    fiber = models.DecimalField("fibra / 100 g", max_digits=5, decimal_places=1, null=True, blank=True)
    is_liquid = models.BooleanField("es bebida", default=False, help_text="Los valores son por 100 ml.")
    source = models.CharField("origen", max_length=8, choices=Source.choices, default=Source.BASE)
    verified = models.BooleanField("verificado", default=False,
                                   help_text="Revisado por CoreX. Los verificados tienen prioridad al buscar.")
    image_url = models.URLField("imagen", blank=True)
    created_in = models.CharField("creado en (gimnasio)", max_length=63, blank=True)
    times_used = models.PositiveIntegerField("veces usado", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "alimento"
        verbose_name_plural = "alimentos"

    def __str__(self):
        return f"{self.name} ({self.brand})" if self.brand else self.name

    def for_grams(self, grams):
        """Macros para una cantidad en gramos (redondeados a 1 decimal)."""
        g = Decimal(str(grams or 0)) / 100
        return {
            "kcal": round(float(self.kcal * g), 1),
            "protein": round(float(self.protein * g), 1),
            "carbs": round(float(self.carbs * g), 1),
            "fat": round(float(self.fat * g), 1),
            "fiber": round(float(self.fiber * g), 1) if self.fiber is not None else None,
        }

    def per100(self):
        return {"kcal": float(self.kcal), "protein": float(self.protein), "carbs": float(self.carbs),
                "fat": float(self.fat), "fiber": float(self.fiber) if self.fiber is not None else None}

    def set_names(self, aliases=(), learned=False):
        """Mantiene el nombre principal + alias normalizados en FoodName (es lo que se busca)."""
        primary = normalize(f"{self.name} {self.brand}".strip())
        FoodName.objects.filter(food=self, text=primary, is_primary=False).delete()
        FoodName.objects.update_or_create(food=self, is_primary=True, defaults={"text": primary})
        for a in aliases:
            t = normalize(a)
            if t and t != primary:
                FoodName.objects.get_or_create(food=self, text=t, defaults={"learned": learned})


class FoodName(models.Model):
    food = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="names")
    text = models.CharField(max_length=200)
    is_primary = models.BooleanField(default=False)
    learned = models.BooleanField("aprendido de correcciones", default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["food", "text"], name="foodname_unique_text")]
        indexes = [GinIndex(fields=["text"], name="foodname_text_trgm", opclasses=["gin_trgm_ops"])]
        verbose_name = "nombre / alias"
        verbose_name_plural = "nombres y alias"

    def __str__(self):
        return self.text


class FoodPortion(models.Model):
    food = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="portions")
    label = models.CharField("porción", max_length=40, help_text="Ej: unidad, taza, cucharada, rebanada")
    grams = models.DecimalField("gramos", max_digits=6, decimal_places=1)

    class Meta:
        ordering = ("grams",)
        constraints = [models.UniqueConstraint(fields=["food", "label"], name="foodportion_unique_label")]
        verbose_name = "porción"
        verbose_name_plural = "porciones"

    def __str__(self):
        return f"{self.label} ({self.grams} g)"
