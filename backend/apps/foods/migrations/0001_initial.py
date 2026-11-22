from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Escrita a mano: necesita activar pg_trgm antes de crear el índice de búsqueda difusa."""

    initial = True
    dependencies = []

    operations = [
        TrigramExtension(),
        migrations.CreateModel(
            name="FoodItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ref", models.CharField(blank=True, help_text="Identificador estable de la carga base o importada (para actualizarla).", max_length=80, null=True, unique=True, verbose_name="referencia")),
                ("name", models.CharField(max_length=160, verbose_name="nombre")),
                ("brand", models.CharField(blank=True, max_length=80, verbose_name="marca")),
                ("barcode", models.CharField(blank=True, max_length=32, null=True, unique=True, verbose_name="código de barras")),
                ("category", models.CharField(choices=[("cereales", "Cereales, panes y pastas"), ("legumbres", "Legumbres"), ("tuberculos", "Papa, batata y choclo"), ("carnes", "Carnes"), ("pescados", "Pescados y mariscos"), ("huevos", "Huevos"), ("lacteos", "Lácteos"), ("frutas", "Frutas"), ("verduras", "Verduras"), ("grasas", "Aceites y grasas"), ("frutos_secos", "Frutos secos y semillas"), ("dulces", "Dulces y snacks"), ("bebidas", "Bebidas"), ("platos", "Platos preparados"), ("suplementos", "Suplementos"), ("otros", "Otros")], default="otros", max_length=16, verbose_name="categoría")),
                ("kcal", models.DecimalField(decimal_places=1, max_digits=6, verbose_name="kcal / 100 g")),
                ("protein", models.DecimalField(decimal_places=1, default=0, max_digits=5, verbose_name="proteínas / 100 g")),
                ("carbs", models.DecimalField(decimal_places=1, default=0, max_digits=5, verbose_name="carbohidratos / 100 g")),
                ("fat", models.DecimalField(decimal_places=1, default=0, max_digits=5, verbose_name="grasas / 100 g")),
                ("fiber", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="fibra / 100 g")),
                ("is_liquid", models.BooleanField(default=False, help_text="Los valores son por 100 ml.", verbose_name="es bebida")),
                ("source", models.CharField(choices=[("base", "Base CoreX"), ("import", "Importado (tabla oficial)"), ("off", "Open Food Facts"), ("user", "Cargado por un usuario"), ("ia", "Estimado por IA")], default="base", max_length=8, verbose_name="origen")),
                ("verified", models.BooleanField(default=False, help_text="Revisado por CoreX. Los verificados tienen prioridad al buscar.", verbose_name="verificado")),
                ("image_url", models.URLField(blank=True, verbose_name="imagen")),
                ("created_in", models.CharField(blank=True, max_length=63, verbose_name="creado en (gimnasio)")),
                ("times_used", models.PositiveIntegerField(default=0, verbose_name="veces usado")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "alimento", "verbose_name_plural": "alimentos", "ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="FoodName",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(max_length=200)),
                ("is_primary", models.BooleanField(default=False)),
                ("learned", models.BooleanField(default=False, verbose_name="aprendido de correcciones")),
                ("food", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="names", to="foods.fooditem")),
            ],
            options={
                "verbose_name": "nombre / alias",
                "verbose_name_plural": "nombres y alias",
                "indexes": [GinIndex(fields=["text"], name="foodname_text_trgm", opclasses=["gin_trgm_ops"])],
                "constraints": [models.UniqueConstraint(fields=("food", "text"), name="foodname_unique_text")],
            },
        ),
        migrations.CreateModel(
            name="FoodPortion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(help_text="Ej: unidad, taza, cucharada, rebanada", max_length=40, verbose_name="porción")),
                ("grams", models.DecimalField(decimal_places=1, max_digits=6, verbose_name="gramos")),
                ("food", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="portions", to="foods.fooditem")),
            ],
            options={
                "verbose_name": "porción",
                "verbose_name_plural": "porciones",
                "ordering": ("grams",),
                "constraints": [models.UniqueConstraint(fields=("food", "label"), name="foodportion_unique_label")],
            },
        ),
    ]
