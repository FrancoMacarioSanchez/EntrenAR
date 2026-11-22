"""API del entrenador: alumnos, rutinas, ejercicios, mediciones y feedback."""
from datetime import timedelta

from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.models import GymSettings
from apps.core.notify import notify
from apps.members.models import Member, MemberNote
from apps.training.models import Exercise, PersonalRecord, Routine, WorkoutSession
from apps.training.services import duplicate_routine, exercise_history, save_routine

from . import data as J
from .permissions import IsTrainer
from .views import _create_measurement, progress_data


def students_qs(user):
    qs = Member.objects.exclude(status="suspended")
    if not user.is_manager and not GymSettings.get().trainers_see_all_members:
        qs = qs.filter(trainer=user)
    return qs


@api_view(["GET"])
@permission_classes([IsTrainer])
def students(request):
    qs = students_qs(request.user).select_related("trainer").annotate(
        last_session=Max("sessions__date"), last_visit=Max("checkins__created_at", filter=Q(checkins__allowed=True)))
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(dni__icontains=q))
    if request.GET.get("mine") == "1":
        qs = qs.filter(trainer=request.user)
    today = timezone.localdate()
    routines = {r.member_id: r for r in Routine.objects.filter(is_active=True, member__isnull=False)}
    out = []
    for m in qs[:400]:
        d = J.member_json(request, m)
        r = routines.get(m.pk)
        d.update({
            "last_session": m.last_session, "last_visit": m.last_visit,
            "days_without_training": (today - m.last_session).days if m.last_session else None,
            "routine": {"id": r.pk, "name": r.name, "start_date": r.start_date} if r else None,
            "routine_age_days": (today - r.start_date).days if r else None,
        })
        flags = []
        if not r:
            flags.append("sin_rutina")
        elif d["routine_age_days"] and d["routine_age_days"] > 56:
            flags.append("rutina_vieja")
        if d["days_without_training"] is None or d["days_without_training"] > 7:
            flags.append("no_entrena")
        if d["membership_state"] in ("expired", "none"):
            flags.append("cuota_vencida")
        d["flags"] = flags
        out.append(d)
    return Response({"results": out})


@api_view(["GET"])
@permission_classes([IsTrainer])
def student_detail(request, pk):
    m = get_object_or_404(students_qs(request.user), pk=pk)
    routines = m.routines.select_related("trainer", "member").prefetch_related("days__exercises__exercise")[:10]
    sessions = m.sessions.select_related("routine_day").prefetch_related("sets__exercise")[:20]
    from apps.members import avatar as av

    return Response({
        "avatar_morph": av.morph_weights(av.clean(m.avatar, sex=m.sex), m.measurements.first()),
        "member": J.member_json(request, m, full=True),
        "routines": [J.routine_json(request, r) for r in routines],
        "sessions": [J.session_json(s) for s in sessions],
        "progress": progress_data(m),
        "measurements": [J.measurement_json(request, x) for x in m.measurements.select_related("recorded_by")[:20]],
        "notes": [{"id": n.pk, "text": n.text, "author": str(n.author) if n.author else "", "date": n.created_at,
                   "visible_to_member": n.visible_to_member} for n in m.member_notes.select_related("author")[:30]],
    })


@api_view(["GET"])
@permission_classes([IsTrainer])
def student_exercise_history(request, pk, ex_id):
    m = get_object_or_404(students_qs(request.user), pk=pk)
    return Response({"exercise": J.exercise_json(request, get_object_or_404(Exercise, pk=ex_id)),
                     "history": exercise_history(m, ex_id)})


@api_view(["POST"])
@permission_classes([IsTrainer])
def student_note(request, pk):
    m = get_object_or_404(students_qs(request.user), pk=pk)
    text = (request.data.get("text") or "").strip()
    if not text:
        return Response({"detail": "Escribí la nota."}, status=400)
    visible = bool(request.data.get("visible_to_member"))
    n = MemberNote.objects.create(member=m, author=request.user, text=text, visible_to_member=visible)
    if visible and m.user:
        notify(m.user, f"Mensaje de {request.user.first_name or 'tu entrenador'}", text[:200], "/app/", kind="note")
    return Response({"id": n.pk}, status=201)


@api_view(["POST"])
@permission_classes([IsTrainer])
def student_measurement(request, pk):
    from apps.body.validation import MeasurementError

    m = get_object_or_404(students_qs(request.user), pk=pk)
    try:
        x = _create_measurement(request, m, request.data)
    except MeasurementError as e:
        return Response({"detail": str(e), "errors": e.errors}, status=400)
    return Response(J.measurement_json(request, x), status=201)


@api_view(["POST"])
@permission_classes([IsTrainer])
def student_assign(request, pk):
    m = get_object_or_404(Member, pk=pk)
    m.trainer = request.user
    m.save(update_fields=["trainer"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsTrainer])
def session_feedback(request, pk):
    s = get_object_or_404(WorkoutSession, pk=pk, member__in=students_qs(request.user))
    s.trainer_feedback = (request.data.get("text") or "")[:2000]
    s.feedback_by = request.user
    s.save(update_fields=["trainer_feedback", "feedback_by"])
    if s.member.user:
        notify(s.member.user, "Tu entrenador comentó tu entrenamiento", s.trainer_feedback[:200], "/app/progreso",
               kind="feedback")
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsTrainer])
def feed(request):
    """Actividad reciente de los alumnos: entrenamientos y récords."""
    since = timezone.now() - timedelta(days=7)
    members = students_qs(request.user)
    if request.GET.get("mine") == "1":
        members = members.filter(trainer=request.user)
    sessions = (WorkoutSession.objects.filter(member__in=members, started_at__gte=since)
                .select_related("member", "routine_day").order_by("-started_at")[:40])
    prs = (PersonalRecord.objects.filter(member__in=members, achieved_at__gte=since)
           .select_related("member", "exercise")[:40])
    return Response({
        "sessions": [{**J.session_json(s, with_sets=False), "member": s.member_id, "member_name": s.member.full_name}
                     for s in sessions],
        "records": [{**J.record_json(r), "member": r.member_id, "member_name": r.member.full_name} for r in prs],
    })


# ------------------------------------------------------------------ rutinas
@api_view(["GET", "POST"])
@permission_classes([IsTrainer])
def routines(request):
    if request.method == "POST":
        r = save_routine(request.data, trainer=request.user)
        return Response(J.routine_json(request, r), status=201)
    qs = Routine.objects.select_related("member", "trainer").prefetch_related("days__exercises__exercise")
    if request.GET.get("templates") == "1":
        qs = qs.filter(is_template=True)
    elif request.GET.get("member"):
        qs = qs.filter(member_id=request.GET["member"])
    else:
        qs = qs.filter(Q(trainer=request.user) | Q(is_template=True))
    return Response({"results": [J.routine_json(request, r) for r in qs[:100]]})


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsTrainer])
def routine_detail(request, pk):
    r = get_object_or_404(Routine.objects.select_related("member", "trainer"), pk=pk)
    if request.method == "PUT":
        r = save_routine(request.data, trainer=request.user, routine=r)
        return Response(J.routine_json(request, r))
    if request.method == "DELETE":
        if WorkoutSession.objects.filter(routine_day__routine=r).exists():
            r.is_active = False
            r.save(update_fields=["is_active"])
        else:
            r.delete()
        return Response(status=204)
    return Response(J.routine_json(request, r))


@api_view(["POST"])
@permission_classes([IsTrainer])
def routine_duplicate(request, pk):
    src = get_object_or_404(Routine, pk=pk)
    member = Member.objects.filter(pk=request.data.get("member")).first() if request.data.get("member") else None
    r = duplicate_routine(src, member=member, trainer=request.user, as_template=bool(request.data.get("as_template")),
                          name=request.data.get("name"))
    return Response(J.routine_json(request, r), status=201)


# ------------------------------------------------------------------ ejercicios
@api_view(["POST"])
@permission_classes([IsTrainer])
def exercise_create(request):
    d = request.data
    if not d.get("name"):
        return Response({"detail": "Falta el nombre."}, status=400)
    if Exercise.objects.filter(name__iexact=d["name"].strip()).exists():
        return Response({"detail": "Ya existe un ejercicio con ese nombre."}, status=400)
    e = Exercise.objects.create(
        name=d["name"].strip()[:100], muscle_group=d.get("muscle_group") or "full_body",
        equipment=d.get("equipment") or "other", tracking=d.get("tracking") or "weight_reps",
        secondary_muscles=d.get("secondary_muscles", "")[:150], instructions=d.get("instructions", ""),
        video_url=d.get("video_url", ""), created_by=request.user)
    return Response(J.exercise_json(request, e), status=201)


@api_view(["GET"])
@permission_classes([IsTrainer])
def choices(request):
    return Response({"muscles": Exercise.Muscle.choices, "equipment": Exercise.Equipment.choices,
                     "tracking": Exercise.Tracking.choices, "goals": Member.Goal.choices})


# ------------------------------------------------------------------ clases del entrenador
def my_classes_qs(user):
    from apps.classes.models import GymClass

    qs = GymClass.objects.filter(is_active=True).select_related("trainer")
    return qs if user.is_manager else qs.filter(trainer=user)


def class_json(gc):
    return {"id": gc.pk, "name": gc.name, "description": gc.description, "weekday": gc.weekday,
            "weekday_label": gc.get_weekday_display(), "time": gc.start_time.strftime("%H:%M"),
            "duration": gc.duration_min, "capacity": gc.capacity, "room": gc.room, "color": gc.color,
            "trainer": gc.trainer.get_full_name() if gc.trainer_id else None}


@api_view(["GET"])
@permission_classes([IsTrainer])
def my_classes(request):
    from apps.classes.models import ClassCancellation

    days = min(int(request.GET.get("days", 14)), 60)
    today = timezone.localdate()
    classes = list(my_classes_qs(request.user))
    cancelled = {(c.gym_class_id, c.date): c.reason for c in ClassCancellation.objects.filter(
        gym_class__in=classes, date__gte=today, date__lte=today + timedelta(days=days))}
    out = []
    for i in range(days):
        d = today + timedelta(days=i)
        for gc in classes:
            if gc.weekday != d.weekday():
                continue
            bk = gc.bookings.filter(date=d)
            out.append({**class_json(gc), "date": d, "booked": bk.filter(status__in=["booked", "attended"]).count(),
                        "waitlist": bk.filter(status="waitlist").count(),
                        "attended": bk.filter(status="attended").count(),
                        "cancelled": (gc.pk, d) in cancelled, "cancel_reason": cancelled.get((gc.pk, d), "")})
    out.sort(key=lambda x: (x["date"], x["time"]))
    return Response({"results": out, "classes": [class_json(gc) for gc in classes]})


@api_view(["GET", "POST"])
@permission_classes([IsTrainer])
def class_occurrence(request, pk, date):
    from django.utils.dateparse import parse_date

    from apps.classes.models import ClassBooking
    from apps.classes.services import cancel, force_add, restore_occurrence, suspend_occurrence

    gc = get_object_or_404(my_classes_qs(request.user), pk=pk)
    d = parse_date(date)
    if not d or d.weekday() != gc.weekday:
        return Response({"detail": "La clase no se dicta ese día."}, status=400)
    if request.method == "POST":
        a = request.data.get("action")
        if a in ("attended", "no_show", "booked"):
            b = get_object_or_404(ClassBooking, pk=request.data.get("booking"), gym_class=gc, date=d)
            b.status = a
            b.save(update_fields=["status"])
        elif a == "all_attended":
            gc.bookings.filter(date=d, status="booked").update(status="attended")
        elif a == "remove":
            b = get_object_or_404(ClassBooking, pk=request.data.get("booking"), gym_class=gc, date=d)
            cancel(b, by_staff=True)
        elif a == "add":
            m = get_object_or_404(Member, pk=request.data.get("member"))
            force_add(gc, m, d)
        elif a == "suspend":
            suspend_occurrence(gc, d, (request.data.get("reason") or "")[:200], request.user)
        elif a == "restore":
            restore_occurrence(gc, d)
        else:
            return Response({"detail": "Acción desconocida."}, status=400)
    canc = gc.cancellation(d)
    bookings = gc.bookings.filter(date=d).select_related("member").order_by("status", "created_at")
    return Response({
        **class_json(gc), "date": d, "cancelled": bool(canc), "cancel_reason": canc.reason if canc else "",
        "bookings": [{"id": b.pk, "status": b.status, "status_label": b.get_status_display(), "member": b.member_id,
                      "name": b.member.full_name, "initials": b.member.initials,
                      "photo": J.media(request, b.member.photo), "phone": b.member.phone} for b in bookings],
    })


@api_view(["PATCH"])
@permission_classes([IsTrainer])
def class_edit(request, pk):
    gc = get_object_or_404(my_classes_qs(request.user), pk=pk)
    d = request.data
    for f, cast in (("capacity", int), ("duration_min", int), ("room", str), ("description", str)):
        if f in d and d[f] not in (None, ""):
            try:
                setattr(gc, f, cast(d[f]))
            except (TypeError, ValueError):
                return Response({"detail": f"Valor inválido en {f}."}, status=400)
    if gc.capacity < 1 or gc.capacity > 500:
        return Response({"detail": "El cupo debe estar entre 1 y 500."}, status=400)
    gc.save()
    return Response(class_json(gc))
