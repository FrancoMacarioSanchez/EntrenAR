from django.urls import path

from . import api as n

urlpatterns = [
    path("me/nutrition/profile/", n.my_profile),
    path("me/nutrition/day/", n.my_day),
    path("me/nutrition/analyze/", n.analyze),
    path("me/nutrition/meals/", n.meals),
    path("me/nutrition/meals/<int:pk>/", n.meal_detail),
    path("me/nutrition/meals/<int:pk>/habitual/", n.meal_habitual),
    path("me/nutrition/copy/", n.copy),
    path("me/nutrition/saved/", n.saved_list),
    path("me/nutrition/saved/<int:pk>/", n.saved_detail),
    path("me/nutrition/recent/", n.recent_foods),
    path("me/nutrition/stats/", n.my_stats),
    path("foods/search/", n.foods_search),
    path("foods/barcode/<str:code>/", n.foods_barcode),
    path("foods/", n.foods_create),
    path("trainer/nutrition/", n.trainer_board),
    path("trainer/students/<int:pk>/nutrition/", n.trainer_student),
]
