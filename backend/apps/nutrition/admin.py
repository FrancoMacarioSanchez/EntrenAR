from django.contrib import admin

from .models import AIRequest, MealLog, MealLogItem, NutritionProfile, SavedMeal


class MealLogItemInline(admin.TabularInline):
    model = MealLogItem
    extra = 0


@admin.register(MealLog)
class MealLogAdmin(admin.ModelAdmin):
    list_display = ("member", "date", "meal_type", "source", "created_at")
    list_filter = ("meal_type", "source", "date")
    inlines = [MealLogItemInline]


@admin.register(NutritionProfile)
class NutritionProfileAdmin(admin.ModelAdmin):
    list_display = ("member", "goal", "calories", "protein_g", "carbs_g", "fat_g", "is_custom", "updated_at")


@admin.register(AIRequest)
class AIRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "status", "model", "tokens_in", "tokens_out", "latency_ms", "created_at")
    list_filter = ("kind", "status", "model")


admin.site.register(SavedMeal)
