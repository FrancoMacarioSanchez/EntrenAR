"""Conversión de modelos a JSON para la PWA (dicts explícitos, sin magia)."""
from django.conf import settings

from apps.core.models import GymSettings


def f(v):
    return float(v) if v is not None else None


def media(request, field):
    if not field:
        return None
    try:
        return request.build_absolute_uri(field.url)
    except ValueError:
        return None


def user_json(request, u):
    return {"id": u.pk, "username": u.username, "first_name": u.first_name, "last_name": u.last_name,
            "name": u.get_full_name() or u.username, "role": u.role, "email": u.email,
            "must_change_password": u.must_change_password, "avatar": media(request, u.avatar),
            "is_trainer": u.is_trainer or u.is_manager, "is_manager": u.is_manager}


def gym_json(request):
    cfg = GymSettings.get()
    return {"name": cfg.display_name, "logo": media(request, cfg.logo), "primary_color": cfg.primary_color,
            "accent_color": cfg.accent_color, "welcome_message": cfg.welcome_message, "whatsapp": cfg.whatsapp,
            "phone": cfg.phone, "address": cfg.address, "instagram": cfg.instagram, "opening_hours": cfg.opening_hours,
            "vapid_public_key": settings.VAPID_PUBLIC_KEY, "mp_enabled": bool(cfg.mp_access_token),
            "students_can_edit_routine": cfg.students_can_edit_routine,
            "self_checkin_enabled": cfg.self_checkin_enabled,
            "checkin_require_location": cfg.checkin_require_location and cfg.latitude is not None,
            **_nutrition_flags(request)}


def _nutrition_flags(request):
    from apps.nutrition import services as ns
    addon = ns.ai_addon(request)
    return {"nutrition": ns.enabled(request), "nutrition_ai": bool(addon and addon.enabled)}


def member_json(request, m, full=False):
    st, mem = m.membership_state()
    out = {"id": m.pk, "first_name": m.first_name, "last_name": m.last_name, "name": m.full_name,
           "initials": m.initials, "photo": media(request, m.photo), "sex": m.sex, "age": m.age,
           "height_cm": f(m.height_cm), "goal": m.goal, "goal_label": m.get_goal_display(), "status": m.status,
           "membership_state": st, "membership_end": mem.end_date if mem else None,
           "plan": mem.plan.name if mem else None, "trainer": m.trainer.get_full_name() if m.trainer else None,
           "trainer_id": m.trainer_id, "avatar": m.avatar or {}}
    if full:
        out.update({"dni": m.dni, "email": m.email, "phone": m.phone, "birth_date": m.birth_date,
                    "medical_notes": m.medical_notes, "medical_ok": m.medical_ok,
                    "medical_clearance_until": m.medical_clearance_until, "joined_at": m.joined_at,
                    "emergency_name": m.emergency_name, "emergency_phone": m.emergency_phone,
                    "access_code": m.access_code})
    return out


def exercise_json(request, e):
    return {"id": e.pk, "name": e.name, "muscle_group": e.muscle_group, "muscle_label": e.get_muscle_group_display(),
            "secondary_muscles": e.secondary_muscles, "equipment": e.equipment,
            "equipment_label": e.get_equipment_display(), "tracking": e.tracking, "instructions": e.instructions,
            "video_url": e.video_url, "image": media(request, e.image)}


def rex_json(request, rex):
    return {"id": rex.pk, "exercise": exercise_json(request, rex.exercise), "order": rex.order, "sets": rex.sets,
            "reps_min": rex.reps_min, "reps_max": rex.reps_max, "reps_label": rex.reps_label,
            "to_failure": rex.to_failure, "target_weight": f(rex.target_weight),
            "duration_seconds": rex.duration_seconds, "rest_seconds": rex.rest_seconds, "tempo": rex.tempo,
            "rpe_target": f(rex.rpe_target), "superset_group": rex.superset_group, "notes": rex.notes}


def routine_json(request, r, member=None, with_perf=False):
    from apps.training.services import last_performance, suggestion

    days = []
    for d in r.days.all():
        exs = []
        for rex in d.exercises.all():
            item = rex_json(request, rex)
            if with_perf and member:
                last = last_performance(member, rex.exercise_id)
                item["last"] = last
                item["suggestion"] = suggestion(rex, last)
            exs.append(item)
        days.append({"id": d.pk, "name": d.name, "order": d.order, "notes": d.notes, "exercises": exs})
    return {"id": r.pk, "name": r.name, "goal": r.goal, "notes": r.notes, "start_date": r.start_date,
            "end_date": r.end_date, "is_active": r.is_active, "is_template": r.is_template, "version": r.version,
            "member": r.member_id, "member_name": r.member.full_name if r.member_id else None,
            "trainer": r.trainer.get_full_name() if r.trainer_id else None, "updated_at": r.updated_at,
            "days": days}


def set_json(s):
    return {"id": s.pk, "client_uuid": str(s.client_uuid), "exercise": s.exercise_id, "exercise_name": s.exercise.name,
            "routine_exercise": s.routine_exercise_id, "set_number": s.set_number, "reps": s.reps,
            "weight": f(s.weight), "duration_seconds": s.duration_seconds, "distance_m": s.distance_m,
            "to_failure": s.to_failure, "rpe": f(s.rpe), "is_warmup": s.is_warmup, "e1rm": s.e1rm}


def session_json(s, with_sets=True):
    out = {"id": s.pk, "client_uuid": str(s.client_uuid), "date": s.date, "started_at": s.started_at,
           "finished_at": s.finished_at, "routine_day": s.routine_day_id,
           "routine_day_name": s.routine_day.name if s.routine_day_id else "Entrenamiento libre",
           "feeling": s.feeling, "notes": s.notes, "trainer_feedback": s.trainer_feedback,
           "duration_min": s.duration_min, "volume": round(s.volume), "sets_count": s.sets.count()}
    if with_sets:
        out["sets"] = [set_json(x) for x in s.sets.select_related("exercise")]
    return out


def record_json(r):
    return {"id": r.pk, "exercise": r.exercise_id, "exercise_name": r.exercise.name, "kind": r.kind,
            "kind_label": r.get_kind_display(), "label": r.label, "value": f(r.value), "weight": f(r.weight),
            "reps": r.reps, "previous_value": f(r.previous_value), "achieved_at": r.achieved_at}


def achievement_json(a):
    return {"code": a.code, "title": a.title, "description": a.description, "icon": a.icon,
            "achieved_at": a.achieved_at}


def measurement_json(request, x):
    from apps.body.models import CIRCUMFERENCES, SKINFOLDS

    out = {"id": x.pk, "date": x.date, "weight_kg": f(x.weight_kg), "height_cm": f(x.height_cm),
           "bioimpedance_bf": f(x.bioimpedance_bf), "notes": x.notes, "bmi": f(x.bmi), "body_fat": f(x.body_fat),
           "body_fat_method": x.body_fat_method, "fat_mass": f(x.fat_mass), "lean_mass": f(x.lean_mass),
           "ffmi": f(x.ffmi), "results": x.results,
           "recorded_by": x.recorded_by.get_full_name() if x.recorded_by_id else None}
    for k, _ in CIRCUMFERENCES + SKINFOLDS:
        out[k] = f(getattr(x, k))
    return out
