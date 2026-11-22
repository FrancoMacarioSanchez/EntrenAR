from django.contrib import admin

from .models import FoodItem, FoodName, FoodPortion


class FoodNameInline(admin.TabularInline):
    model = FoodName
    extra = 1
    fields = ("text", "is_primary", "learned")


class FoodPortionInline(admin.TabularInline):
    model = FoodPortion
    extra = 1


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "kcal", "protein", "carbs", "fat", "source", "verified",
                    "times_used", "created_in")
    list_filter = ("verified", "source", "category", "is_liquid")
    search_fields = ("name", "brand", "barcode", "names__text")
    list_editable = ("verified",)
    readonly_fields = ("times_used", "created_in", "created_at", "updated_at")
    inlines = [FoodNameInline, FoodPortionInline]
    actions = ["mark_verified"]
    ordering = ("verified", "-times_used")

    @admin.action(description="Marcar como verificados")
    def mark_verified(self, request, queryset):
        n = queryset.update(verified=True)
        self.message_user(request, f"{n} alimentos verificados.")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.set_names()
