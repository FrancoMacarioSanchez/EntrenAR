from django.core.management.base import BaseCommand
from django.db import transaction

from apps.foods.models import FoodItem
from apps.foods.seed_data import FOODS


class Command(BaseCommand):
    help = "Carga o actualiza la base inicial de alimentos (se puede correr las veces que haga falta)."

    @transaction.atomic
    def handle(self, *args, **opts):
        created = updated = 0
        for slug, name, cat, kcal, p, c, f, fib, aliases, portions, liquid in FOODS:
            food, new = FoodItem.objects.update_or_create(
                ref=f"base:{slug}",
                defaults={"name": name, "category": cat, "kcal": kcal, "protein": p, "carbs": c, "fat": f,
                          "fiber": fib, "is_liquid": liquid, "source": FoodItem.Source.BASE, "verified": True},
            )
            created += new
            updated += not new
            food.set_names([a for a in aliases.split("|") if a])
            for part in filter(None, portions.split("|")):
                label, grams = part.rsplit(":", 1)
                food.portions.update_or_create(label=label, defaults={"grams": grams})
        self.stdout.write(self.style.SUCCESS(f"Alimentos base: {created} nuevos, {updated} actualizados."))
