"""Rutinas, registro de entrenamientos, récords personales, logros y progresión."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .models import Achievement, Exercise, PersonalRecord, Routine, RoutineDay, RoutineExercise, SetLog, WorkoutSession

D = Decimal


# ------------------------------------------------------------------ Récords
def _prev_sets(set_log):
    return (SetLog.objects.filter(session__member_id=set_log.session.member_id, exercise_id=set_log.exercise_id,
                                  is_warmup=False).exclude(pk=set_log.pk))


def detect_records(set_log):
    """Compara la serie con el historial y crea PersonalRecord. Devuelve los nuevos récords."""
    if set_log.is_warmup or not set_log.reps:
        return []
    member = set_log.session.member
    ex = set_log.exercise
    prev = _prev_sets(set_log)
    if not prev.exists():
        return []
    out = []

    def add(kind, value, previous):
        out.append(PersonalRecord.objects.create(
            member=member, exercise=ex, kind=kind, value=D(str(value)), weight=set_log.weight, reps=set_log.reps,
            previous_value=D(str(previous)) if previous is not None else None, set_log=set_log))

    weight = set_log.weight or D("0")
    if weight > 0:
        best_w = prev.aggregate(m=Max("weight"))["m"] or D("0")
        if weight > best_w:
            add(PersonalRecord.Kind.MAX_WEIGHT, weight, best_w)
        if set_log.reps <= 12:
            best_e = max((s.e1rm for s in prev.filter(reps__lte=12, weight__gt=0)), default=0.0)
            if set_log.e1rm > best_e and weight <= best_w:  # si ya es peso máximo no duplicamos el festejo
                add(PersonalRecord.Kind.E1RM, set_log.e1rm, best_e)
        same = prev.filter(weight=weight).aggregate(m=Max("reps"))["m"]
        if same is not None and set_log.reps > same:
            add(PersonalRecord.Kind.REPS_AT_WEIGHT, set_log.reps, same)
    else:
        best_r = prev.filter(weight__isnull=True).aggregate(m=Max("reps"))["m"]
        best_r0 = prev.filter(weight=0).aggregate(m=Max("reps"))["m"]
        best = max(best_r or 0, best_r0 or 0)
        if best and set_log.reps > best:
            add(PersonalRecord.Kind.MAX_REPS, set_log.reps, best)
    return out


ACHIEVEMENTS = [
    ("first_session", "Primer entrenamiento", "Registraste tu primera sesión", "🎉", lambda c: c["sessions"] >= 1),
    ("sessions_10", "10 entrenamientos", "Ya sumás 10 sesiones", "🔥", lambda c: c["sessions"] >= 10),
    ("sessions_50", "50 entrenamientos", "Constancia de hierro", "💪", lambda c: c["sessions"] >= 50),
    ("sessions_100", "100 entrenamientos", "Club de los 100", "🏅", lambda c: c["sessions"] >= 100),
    ("first_pr", "Primer récord", "Superaste una marca personal", "🏆", lambda c: c["prs"] >= 1),
    ("prs_10", "10 récords", "Progresión imparable", "🚀", lambda c: c["prs"] >= 10),
    ("prs_50", "50 récords", "Máquina de PRs", "👑", lambda c: c["prs"] >= 50),
    ("streak_4", "4 semanas seguidas", "Entrenaste 4 semanas sin cortar", "📅", lambda c: c["week_streak"] >= 4),
    ("streak_12", "12 semanas seguidas", "3 meses de constancia", "⭐", lambda c: c["week_streak"] >= 12),
    ("volume_100k", "100 toneladas", "Levantaste 100.000 kg en total", "🏋️", lambda c: c["volume"] >= 100000),
]


def week_streak(member):
    """Semanas consecutivas con al menos una sesión (la semana actual puede estar todavía vacía)."""
    import datetime as dt

    mondays = {d - dt.timedelta(days=d.weekday()) for d in member.sessions.values_list("date", flat=True)}
    if not mondays:
        return 0
    today = timezone.localdate()
    cur = today - dt.timedelta(days=today.weekday())
    if cur not in mondays:
        cur -= dt.timedelta(days=7)
    streak = 0
    while cur in mondays:
        streak += 1
        cur -= dt.timedelta(days=7)
    return streak


def check_achievements(member):
    sets = SetLog.objects.filter(session__member=member, is_warmup=False, weight__isnull=False, reps__isnull=False)
    ctx = {
        "sessions": member.sessions.count(),
        "prs": member.records.count(),
        "week_streak": week_streak(member),
        "volume": sum(float(w) * r for w, r in sets.values_list("weight", "reps")),
    }
    have = set(member.achievements.values_list("code", flat=True))
    new = []
    for code, title, desc, icon, cond in ACHIEVEMENTS:
        if code not in have and cond(ctx):
            new.append(Achievement.objects.create(member=member, code=code, title=title, description=desc, icon=icon))
    return new


# ------------------------------------------------------------------ Progresión
def last_performance(member, exercise_id, before_session=None):
    qs = WorkoutSession.objects.filter(member=member, sets__exercise_id=exercise_id)
    if before_session:
        qs = qs.exclude(pk=before_session.pk)
    s = qs.order_by("-date", "-started_at").first()
    if not s:
        return None
    sets = [{"set_number": x.set_number, "reps": x.reps, "weight": float(x.weight) if x.weight is not None else None,
             "to_failure": x.to_failure, "rpe": float(x.rpe) if x.rpe is not None else None}
            for x in s.sets.filter(exercise_id=exercise_id, is_warmup=False).order_by("set_number")]
    return {"date": s.date, "sets": sets}


def suggestion(rex, last):
    """Sugerencia de doble progresión: si completó el rango alto en todas las series, subir peso."""
    if not last or not last["sets"]:
        if rex.target_weight:
            return {"weight": float(rex.target_weight), "text": "Peso sugerido por tu entrenador"}
        return None
    sets = last["sets"]
    weights = [s["weight"] for s in sets if s["weight"]]
    top = max(weights) if weights else None
    top_reps = rex.reps_max or rex.reps_min
    if top is None:
        best = max((s["reps"] or 0) for s in sets)
        return {"reps": best + 1, "text": f"La última vez hiciste {best} reps: ¡intentá {best + 1}!"}
    done_all = len(sets) >= rex.sets and all((s["reps"] or 0) >= (top_reps or 0) for s in sets if s["weight"] == top)
    if top_reps and done_all:
        inc = 1.0 if rex.exercise.equipment in ("dumbbell", "cable", "machine") and top < 20 else 2.5
        return {"weight": top + inc, "text": f"Completaste {top_reps} reps con {top:g} kg: subí a {top + inc:g} kg"}
    best = max((s["reps"] or 0) for s in sets if s["weight"] == top)
    return {"weight": top, "text": f"Mantené {top:g} kg y buscá superar {best} reps"}


# ------------------------------------------------------------------ Sesiones (con soporte offline)
def _dt(v):
    if not v:
        return None
    d = parse_datetime(v) if isinstance(v, str) else v
    if d and timezone.is_naive(d):
        d = timezone.make_aware(d)
    return d


def _dec(v):
    if v in (None, ""):
        return None
    return D(str(v))


@transaction.atomic
def save_session(member, data):
    """Guarda/actualiza una sesión desde la PWA. Idempotente por client_uuid (sesión y series)."""
    session, created = WorkoutSession.objects.get_or_create(
        client_uuid=data["client_uuid"],
        defaults={"member": member, "routine_day_id": data.get("routine_day") or None,
                  "date": parse_date(str(data.get("date") or "")) or timezone.localdate(),
                  "started_at": _dt(data.get("started_at")) or timezone.now()},
    )
    if session.member_id != member.pk:
        raise PermissionError("La sesión pertenece a otro alumno.")
    for f in ("feeling", "notes"):
        if f in data and data[f] is not None:
            setattr(session, f, data[f])
    if data.get("finished_at"):
        session.finished_at = _dt(data["finished_at"])
    session.save()

    new_records = []
    for s in data.get("sets", []):
        if s.get("deleted"):
            SetLog.objects.filter(client_uuid=s["client_uuid"], session=session).delete()
            continue
        defaults = {
            "exercise_id": s["exercise"], "routine_exercise_id": s.get("routine_exercise") or None,
            "set_number": s.get("set_number") or 1, "reps": s.get("reps"), "weight": _dec(s.get("weight")),
            "duration_seconds": s.get("duration_seconds"), "distance_m": s.get("distance_m"),
            "to_failure": bool(s.get("to_failure")), "rpe": _dec(s.get("rpe")),
            "is_warmup": bool(s.get("is_warmup")), "created_at": _dt(s.get("created_at")) or timezone.now(),
        }
        log, was_created = SetLog.objects.update_or_create(client_uuid=s["client_uuid"], session=session,
                                                           defaults=defaults)
        if was_created:
            new_records += detect_records(log)
    achievements = check_achievements(member) if session.finished_at else []
    if new_records or achievements:
        _notify_trainer(member, session, new_records)
    return session, new_records, achievements


def _notify_trainer(member, session, records):
    from apps.core.notify import notify

    if member.trainer and records:
        names = ", ".join(sorted({r.exercise.name for r in records}))[:200]
        notify(member.trainer, f"🏆 {member.first_name} hizo récord", names, f"/app/entrenador/alumnos/{member.pk}",
               kind="pr", push=True)


# ------------------------------------------------------------------ Rutinas
@transaction.atomic
def save_routine(payload, *, trainer=None, routine=None):
    """Crea o actualiza una rutina completa (días + ejercicios) desde el constructor.

    Si la rutina ya tiene entrenamientos registrados se crea una NUEVA VERSIÓN y la anterior queda
    archivada, así el historial del alumno no se pierde.
    """
    member_id = payload.get("member") or None
    if routine is not None and WorkoutSession.objects.filter(routine_day__routine=routine).exists():
        old = routine
        old.is_active = False
        old.end_date = timezone.localdate()
        old.save(update_fields=["is_active", "end_date"])
        routine = Routine(parent=old, version=old.version + 1, member_id=old.member_id, trainer=trainer or old.trainer)
    elif routine is None:
        routine = Routine(trainer=trainer, member_id=member_id)

    for f in ("name", "goal", "notes"):
        if f in payload:
            setattr(routine, f, payload[f] or "")
    routine.is_template = bool(payload.get("is_template", routine.is_template))
    if routine.is_template:
        routine.member = None
    elif member_id:
        routine.member_id = member_id
    routine.start_date = parse_date(str(payload.get("start_date") or "")) or routine.start_date or timezone.localdate()
    routine.end_date = parse_date(str(payload.get("end_date") or "")) if payload.get("end_date") else None
    routine.is_active = payload.get("is_active", True)
    routine.save()

    if routine.is_active and routine.member_id:
        Routine.objects.filter(member_id=routine.member_id, is_active=True).exclude(pk=routine.pk).update(
            is_active=False)

    routine.days.all().delete()
    for di, d in enumerate(payload.get("days", [])):
        day = RoutineDay.objects.create(routine=routine, name=d.get("name") or f"Día {di + 1}", order=di,
                                        notes=d.get("notes", "") or "")
        for ei, e in enumerate(d.get("exercises", [])):
            RoutineExercise.objects.create(
                day=day, exercise_id=e["exercise"], order=ei, sets=e.get("sets") or 3,
                reps_min=e.get("reps_min") or None, reps_max=e.get("reps_max") or None,
                to_failure=bool(e.get("to_failure")), target_weight=_dec(e.get("target_weight")),
                duration_seconds=e.get("duration_seconds") or None, rest_seconds=e.get("rest_seconds") or 90,
                tempo=e.get("tempo", "") or "", rpe_target=_dec(e.get("rpe_target")),
                superset_group=(e.get("superset_group") or "")[:2], notes=e.get("notes", "") or "",
            )
    if routine.member_id and routine.member.user:
        from apps.core.notify import notify

        notify(routine.member.user, "Tenés una rutina nueva", routine.name, "/app/rutina", kind="routine")
    return routine


@transaction.atomic
def duplicate_routine(src, *, member=None, trainer=None, as_template=False, name=None):
    payload = routine_payload(src)
    payload.update(member=member.pk if member else None, is_template=as_template, name=name or src.name,
                   start_date=None, end_date=None, is_active=not as_template)
    return save_routine(payload, trainer=trainer)


def routine_payload(r):
    return {
        "name": r.name, "goal": r.goal, "notes": r.notes, "member": r.member_id, "is_template": r.is_template,
        "days": [{
            "name": d.name, "notes": d.notes,
            "exercises": [{
                "exercise": e.exercise_id, "sets": e.sets, "reps_min": e.reps_min, "reps_max": e.reps_max,
                "to_failure": e.to_failure, "target_weight": e.target_weight, "duration_seconds": e.duration_seconds,
                "rest_seconds": e.rest_seconds, "tempo": e.tempo, "rpe_target": e.rpe_target,
                "superset_group": e.superset_group, "notes": e.notes,
            } for e in d.exercises.all()],
        } for d in r.days.all()],
    }


def exercise_history(member, exercise_id, limit=60):
    rows = []
    sessions = (WorkoutSession.objects.filter(member=member, sets__exercise_id=exercise_id).distinct()
                .order_by("-date")[:limit])
    for s in reversed(list(sessions)):
        sets = list(s.sets.filter(exercise_id=exercise_id, is_warmup=False))
        if not sets:
            continue
        rows.append({
            "date": s.date,
            "max_weight": max((float(x.weight or 0) for x in sets), default=0),
            "best_e1rm": max((x.e1rm for x in sets if (x.reps or 0) <= 12), default=0),
            "max_reps": max((x.reps or 0 for x in sets), default=0),
            "volume": round(sum(float(x.weight or 0) * (x.reps or 0) for x in sets), 1),
            "sets": [{"reps": x.reps, "weight": float(x.weight) if x.weight is not None else None,
                      "to_failure": x.to_failure} for x in sets],
        })
    return rows


def active_routine(member):
    return (Routine.objects.filter(member=member, is_active=True, is_template=False)
            .prefetch_related("days__exercises__exercise").first())


def exercise_library():
    return Exercise.objects.filter(is_active=True)
