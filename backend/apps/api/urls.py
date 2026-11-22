from django.urls import include, path

from . import views as v
from . import views_trainer as t

urlpatterns = [
    path("auth/token/", v.LoginView.as_view()),
    path("auth/refresh/", v.RefreshView.as_view()),
    path("auth/info/", v.public_info),
    path("me/", v.me),
    path("me/password/", v.change_password),
    path("me/photo/", v.upload_avatar),
    path("me/avatar/", v.my_avatar),
    path("avatar/schema/", v.avatar_schema),
    path("me/membership/", v.my_membership),
    path("me/checkin/", v.self_checkin),
    path("promotions/", v.promotions),
    path("me/charges/<int:pk>/pay/", v.pay_charge),
    path("me/routine/", v.my_routine),
    path("me/sessions/", v.my_sessions),
    path("me/sessions/<int:pk>/", v.session_detail),
    path("me/sync/", v.sync),
    path("me/progress/", v.my_progress),
    path("me/exercises/<int:pk>/history/", v.my_exercise_history),
    path("me/measurements/", v.my_measurements),
    path("me/measurements/<int:pk>/", v.my_measurement_delete),
    path("me/photos/", v.my_photos),
    path("exercises/", v.exercises),
    path("classes/", v.classes),
    path("classes/<int:pk>/book/", v.class_book),
    path("bookings/<int:pk>/cancel/", v.booking_cancel),
    path("notifications/", v.notifications),
    path("notifications/read/", v.notifications_read),
    path("push/subscribe/", v.push_subscribe),
    path("leaderboard/", v.leaderboard),

    # entrenador
    path("trainer/students/", t.students),
    path("trainer/students/<int:pk>/", t.student_detail),
    path("trainer/students/<int:pk>/notes/", t.student_note),
    path("trainer/students/<int:pk>/measurements/", t.student_measurement),
    path("trainer/students/<int:pk>/assign/", t.student_assign),
    path("trainer/students/<int:pk>/exercises/<int:ex_id>/history/", t.student_exercise_history),
    path("trainer/feed/", t.feed),
    path("trainer/classes/", t.my_classes),
    path("trainer/classes/<int:pk>/", t.class_edit),
    path("trainer/classes/<int:pk>/<str:date>/", t.class_occurrence),
    path("trainer/choices/", t.choices),
    path("trainer/exercises/", t.exercise_create),
    path("trainer/sessions/<int:pk>/feedback/", t.session_feedback),
    path("routines/", t.routines),
    path("routines/<int:pk>/", t.routine_detail),
    path("routines/<int:pk>/duplicate/", t.routine_duplicate),

    # nutrición
    path("", include("apps.nutrition.urls")),
]
