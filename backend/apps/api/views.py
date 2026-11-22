"""API de la PWA: autenticación, perfil y todo lo del alumno."""
from datetime import timedelta

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.billing.models import Charge
from apps.body.models import CIRCUMFERENCES, SKINFOLDS, BodyMeasurement, ProgressPhoto
from apps.classes.models import ClassBooking, GymClass
from apps.classes.services import BookingError, book, cancel
from apps.core.models import Notification, PushSubscription
from apps.training.models import Exercise, PersonalRecord, SetLog, WorkoutSession
from apps.training.services import active_routine, exercise_history, save_session, week_streak

from . import data as J
from .auth import TenantRefreshSerializer, TenantTokenSerializer
from .permissions import IsStudent


class LoginView(TokenObtainPairView):
    serializer_class = TenantTokenSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class RefreshView(TokenRefreshView):
    serializer_class = TenantRefreshSerializer
    permission_classes = [AllowAny]


@api_view(["GET"])
@permission_classes([AllowAny])
def public_info(request):
    return Response({"gym": J.gym_json(request)})


@api_view(["GET"])
def me(request):
    u = request.user
    member = getattr(u, "member", None)
    tenant = request.tenant
    return Response({
        "user": J.user_json(request, u),
        "member": J.member_json(request, member, full=True) if member else None,
        "gym": J.gym_json(request),
        "unread": Notification.objects.filter(user=u, is_read=False).count(),
        "gym_blocked": tenant.is_blocked,
    })


@api_view(["POST"])
def change_password(request):
    u = request.user
    if not u.check_password(request.data.get("old_password", "")):
        return Response({"detail": "La contraseña actual no es correcta."}, status=400)
    new = request.data.get("new_password", "")
    try:
        password_validation.validate_password(new, u)
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    u.set_password(new)
    u.must_change_password = False
    u.save()
    return Response({"ok": True})


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_avatar(request):
    f = request.FILES.get("photo")
    if not f:
        return Response({"detail": "Falta la foto."}, status=400)
    member = getattr(request.user, "member", None)
    if member:
        member.photo = f
        member.save(update_fields=["photo"])
        return Response({"photo": J.media(request, member.photo)})
    request.user.avatar = f
    request.user.save(update_fields=["avatar"])
    return Response({"photo": J.media(request, request.user.avatar)})


@api_view(["GET", "PUT"])
@permission_classes([IsStudent])
def my_avatar(request):
    """Configuración del avatar del alumno + pesos de los morph targets con su última medición."""
    from apps.members import avatar as av

    m = request.user.member
    if request.method == "PUT":
        m.avatar = av.clean(request.data, sex=m.sex)
        update = ["avatar"]
        if m.avatar["sex"] != m.sex:
            m.sex = m.avatar["sex"]
            update.append("sex")
        m.save(update_fields=update)
    cfg = av.clean(m.avatar, sex=m.sex)
    return Response({"avatar": cfg, "sex": m.sex, "morph": av.morph_weights(cfg, m.measurements.first())})


@api_view(["GET"])
def avatar_schema(request):
    from apps.members import avatar as av

    return Response(av.schema())


# ------------------------------------------------------------------ membresía y pagos
@api_view(["GET"])
@permission_classes([IsStudent])
def my_membership(request):
    m = request.user.member
    st, mem = m.membership_state()
    charges = Charge.objects.filter(member=m, status__in=["pending", "partial"]).order_by("due_date")
    payments = m.payments.filter(is_void=False).select_related("method", "charge")[:20]
    return Response({
        "state": st, "access_code": m.access_code,
        "membership": {"plan": mem.plan.name, "start_date": mem.start_date, "end_date": mem.end_date,
                       "remaining_days": mem.remaining_days, "visits_left": mem.visits_left(),
                       "auto_renew": mem.auto_renew, "status": mem.status,
                       "includes_classes": mem.plan.includes_classes} if mem else None,
        "debt": J.f(m.debt),
        "charges": [{"id": c.pk, "concept": c.concept, "amount": J.f(c.amount), "balance": J.f(c.balance),
                     "due_date": c.due_date, "overdue": c.due_date < timezone.localdate()} for c in charges],
        "payments": [{"id": p.pk, "amount": J.f(p.amount), "date": p.paid_at, "method": p.method.name,
                      "concept": p.charge.concept if p.charge else p.notes,
                      "invoice_number": p.invoice_number} for p in payments],
        "checkins_month": m.checkins.filter(allowed=True, created_at__date__gte=timezone.localdate().replace(day=1)).count(),
        "notes": [{"text": n.text, "author": str(n.author) if n.author else "", "date": n.created_at}
                  for n in m.member_notes.filter(visible_to_member=True)[:10]],
        "promotions": promotions_json(),
    })


def promotions_json():
    from apps.memberships.models import Promotion

    today = timezone.localdate()
    out = []
    for p in Promotion.objects.filter(is_active=True, show_in_app=True, starts_on__lte=today).exclude(
            ends_on__lt=today).prefetch_related("plans")[:10]:
        if p.is_current():
            out.append({"id": p.pk, "name": p.name, "description": p.description, "summary": p.summary,
                        "ends_on": p.ends_on, "code": p.code, "color": p.color,
                        "plans": [x.name for x in p.plans.all()], "only_new": p.only_new_members})
    return out


@api_view(["GET"])
def promotions(request):
    return Response({"results": promotions_json()})


@api_view(["POST"])
@permission_classes([IsStudent])
def pay_charge(request, pk):
    from apps.billing.services import mp_create_link

    ch = get_object_or_404(Charge, pk=pk, member=request.user.member)
    try:
        return Response({"url": mp_create_link(ch, request)})
    except Exception as exc:  # noqa: BLE001
        return Response({"detail": f"No se pudo generar el pago: {exc}"}, status=400)


# ------------------------------------------------------------------ autoingreso con QR
@api_view(["POST"])
@permission_classes([IsStudent])
def self_checkin(request):
    from apps.core.models import GymSettings
    from apps.core.selfcheckin import distance_m, verify
    from apps.memberships.services import check_in

    cfg = GymSettings.get()
    if not cfg.self_checkin_enabled:
        return Response({"detail": "El gimnasio no tiene habilitado el ingreso con QR. Mostrá tu QR en recepción."},
                        status=403)
    mode = verify(cfg.checkin_key, request.data.get("k"))
    if not mode:
        return Response({"detail": "El QR no es válido o ya venció. Volvé a escanear el código del gimnasio."},
                        status=400)
    if mode == "static" and cfg.checkin_require_location and cfg.latitude is not None:
        lat, lng = request.data.get("lat"), request.data.get("lng")
        if lat is None or lng is None:
            return Response({"detail": "Necesitamos tu ubicación para confirmar que estás en el gimnasio.",
                             "code": "location_required"}, status=400)
        d = distance_m(float(lat), float(lng), float(cfg.latitude), float(cfg.longitude))
        if d > cfg.checkin_radius_m:
            return Response({"detail": f"Parece que no estás en el gimnasio (a {round(d)} m).",
                             "code": "too_far"}, status=400)
    member = request.user.member
    c, allowed, reason, m = check_in(member, method="app", user=request.user)
    return Response({
        "allowed": allowed, "reason": reason, "name": member.first_name, "at": c.created_at,
        "plan": m.plan.name if m else None, "end_date": m.end_date if m else None,
        "visits_left": m.visits_left() if m else None, "debt": J.f(member.debt),
        "already": reason == "Ya registró su ingreso",
    })


# ------------------------------------------------------------------ entrenamiento
@api_view(["GET"])
@permission_classes([IsStudent])
def my_routine(request):
    member = request.user.member
    r = active_routine(member)
    if not r:
        return Response({"routine": None})
    data = J.routine_json(request, r, member=member, with_perf=True)
    # sugerir el día que toca: el siguiente al último entrenado
    last = member.sessions.filter(routine_day__routine=r).order_by("-date", "-started_at").first()
    ids = [d["id"] for d in data["days"]]
    nxt = ids[0] if ids else None
    if last and last.routine_day_id in ids:
        nxt = ids[(ids.index(last.routine_day_id) + 1) % len(ids)]
    data["next_day"] = nxt
    return Response({"routine": data})


@api_view(["GET", "POST"])
@permission_classes([IsStudent])
def my_sessions(request):
    member = request.user.member
    if request.method == "POST":
        return _save_session(request, member, request.data)
    qs = member.sessions.select_related("routine_day").prefetch_related("sets__exercise")[:40]
    return Response({"results": [J.session_json(s, with_sets=request.GET.get("sets") == "1") for s in qs]})


def _save_session(request, member, payload):
    if not payload.get("client_uuid"):
        return Response({"detail": "Falta client_uuid."}, status=400)
    try:
        session, records, achievements = save_session(member, payload)
    except PermissionError as e:
        return Response({"detail": str(e)}, status=403)
    return Response({"session": J.session_json(session), "records": [J.record_json(r) for r in records],
                     "achievements": [J.achievement_json(a) for a in achievements]}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsStudent])
def sync(request):
    """Cola offline: recibe varias operaciones juntas y devuelve el resultado de cada una."""
    member = request.user.member
    out = []
    for op in request.data.get("ops", []):
        kind, payload = op.get("type"), op.get("payload") or {}
        try:
            if kind == "session":
                session, records, ach = save_session(member, payload)
                out.append({"id": op.get("id"), "ok": True, "records": [J.record_json(r) for r in records],
                            "achievements": [J.achievement_json(a) for a in ach], "session_id": session.pk})
            elif kind == "measurement":
                from apps.body.validation import MeasurementError

                try:
                    x = _create_measurement(request, member, payload)
                except MeasurementError as e:  # datos inválidos: no tiene sentido reintentar
                    out.append({"id": op.get("id"), "ok": False, "fatal": True, "type": kind, "error": str(e)})
                    continue
                out.append({"id": op.get("id"), "ok": True, "measurement": J.measurement_json(request, x)})
            else:
                out.append({"id": op.get("id"), "ok": False, "error": "tipo desconocido"})
        except Exception as exc:  # noqa: BLE001
            out.append({"id": op.get("id"), "ok": False, "error": str(exc)[:200]})
    return Response({"results": out})


@api_view(["GET"])
@permission_classes([IsStudent])
def session_detail(request, pk):
    s = get_object_or_404(WorkoutSession, pk=pk, member=request.user.member)
    return Response(J.session_json(s))


@api_view(["GET"])
@permission_classes([IsStudent])
def my_progress(request):
    return Response(progress_data(request.user.member))


def progress_data(member):
    today = timezone.localdate()
    sets = SetLog.objects.filter(session__member=member, is_warmup=False)
    weeks = []
    for i in range(11, -1, -1):
        start = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        end = start + timedelta(days=6)
        ws = sets.filter(session__date__gte=start, session__date__lte=end)
        vol = sum(float(w or 0) * (r or 0) for w, r in ws.values_list("weight", "reps"))
        weeks.append({"week": start, "volume": round(vol), "sessions": member.sessions.filter(
            date__gte=start, date__lte=end).count()})
    per_ex = (sets.values("exercise", "exercise__name", "exercise__muscle_group").annotate(
        n=Count("id"), last=Max("session__date"), top=Max("weight")).order_by("-n")[:40])
    muscles = {}
    for r in sets.filter(session__date__gte=today - timedelta(days=30)).values("exercise__muscle_group").annotate(
            n=Count("id")):
        muscles[dict(Exercise.Muscle.choices).get(r["exercise__muscle_group"], r["exercise__muscle_group"])] = r["n"]
    return {
        "sessions_total": member.sessions.count(),
        "sessions_month": member.sessions.filter(date__gte=today.replace(day=1)).count(),
        "week_streak": week_streak(member),
        "total_volume": round(sum(float(w or 0) * (r or 0) for w, r in sets.values_list("weight", "reps"))),
        "weeks": weeks,
        "exercises": [{"id": r["exercise"], "name": r["exercise__name"], "muscle": r["exercise__muscle_group"],
                       "sets": r["n"], "last": r["last"], "top_weight": J.f(r["top"])} for r in per_ex],
        "muscles_30d": muscles,
        "records": [J.record_json(r) for r in PersonalRecord.objects.filter(member=member).select_related("exercise")[:30]],
        "achievements": [J.achievement_json(a) for a in member.achievements.all()],
        "checkins_30d": member.checkins.filter(allowed=True, created_at__gte=timezone.now() - timedelta(days=30)).count(),
    }


@api_view(["GET"])
@permission_classes([IsStudent])
def my_exercise_history(request, pk):
    ex = get_object_or_404(Exercise, pk=pk)
    records = PersonalRecord.objects.filter(member=request.user.member, exercise=ex).select_related("exercise")[:20]
    return Response({"exercise": J.exercise_json(request, ex), "history": exercise_history(request.user.member, pk),
                     "records": [J.record_json(r) for r in records]})


@api_view(["GET"])
def exercises(request):
    qs = Exercise.objects.filter(is_active=True)
    return Response({"results": [J.exercise_json(request, e) for e in qs]})


# ------------------------------------------------------------------ cuerpo
MEASURE_FIELDS = [k for k, _ in CIRCUMFERENCES + SKINFOLDS] + ["weight_kg", "height_cm", "bioimpedance_bf",
                                                                 "resting_hr", "notes"]


def _create_measurement(request, member, payload):
    """Crea la medición validada. Lanza MeasurementError con mensajes claros."""
    from apps.body.validation import clean_measurement

    if payload.get("client_uuid"):
        existing = BodyMeasurement.objects.filter(client_uuid=payload["client_uuid"], member=member).first()
        if existing:
            return existing
    date, values = clean_measurement(payload)
    if payload.get("sex") in ("M", "F") and payload["sex"] != member.sex:
        member.sex = payload["sex"]
        member.save(update_fields=["sex"])
    x = BodyMeasurement(member=member, recorded_by=request.user, client_uuid=payload.get("client_uuid") or None,
                        date=date, notes=str(payload.get("notes") or "")[:250], **values)
    x.save()
    return x


def measurement_error(e):
    return Response({"detail": str(e), "errors": e.errors}, status=400)


@api_view(["GET", "POST"])
@permission_classes([IsStudent])
def my_measurements(request):
    member = request.user.member
    if request.method == "POST":
        from apps.body.validation import MeasurementError

        try:
            x = _create_measurement(request, member, request.data)
        except MeasurementError as e:
            return measurement_error(e)
        return Response(J.measurement_json(request, x), status=201)
    qs = member.measurements.select_related("recorded_by")[:60]
    return Response({"results": [J.measurement_json(request, x) for x in qs],
                     "member": {"sex": member.sex, "age": member.age, "height_cm": J.f(member.height_cm),
                                "avatar": member.avatar or {}}})


@api_view(["DELETE"])
@permission_classes([IsStudent])
def my_measurement_delete(request, pk):
    get_object_or_404(BodyMeasurement, pk=pk, member=request.user.member).delete()
    return Response(status=204)


@api_view(["GET", "POST"])
@permission_classes([IsStudent])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def my_photos(request):
    member = request.user.member
    if request.method == "POST":
        img = request.FILES.get("image")
        if not img:
            return Response({"detail": "Falta la imagen."}, status=400)
        p = ProgressPhoto.objects.create(member=member, image=img, pose=request.data.get("pose", "front"),
                                         date=parse_date(request.data.get("date", "")) or timezone.localdate())
        return Response({"id": p.pk, "image": J.media(request, p.image), "date": p.date, "pose": p.pose}, status=201)
    return Response({"results": [{"id": p.pk, "image": J.media(request, p.image), "date": p.date, "pose": p.pose,
                                  "pose_label": p.get_pose_display()} for p in member.photos.all()[:60]]})


# ------------------------------------------------------------------ clases
@api_view(["GET"])
@permission_classes([IsStudent])
def classes(request):
    member = request.user.member
    today = timezone.localdate()
    days = []
    my = {(b.gym_class_id, b.date): b for b in ClassBooking.objects.filter(
        member=member, date__gte=today, date__lte=today + timedelta(days=7)).exclude(status="cancelled")}
    gcs = list(GymClass.objects.filter(is_active=True).select_related("trainer"))
    from apps.classes.models import ClassCancellation

    cancelled = {(c.gym_class_id, c.date): c.reason for c in ClassCancellation.objects.filter(
        date__gte=today, date__lte=today + timedelta(days=7))}
    for i in range(7):
        d = today + timedelta(days=i)
        items = []
        for gc in gcs:
            if gc.weekday != d.weekday():
                continue
            start = gc.starts_at(d)
            if start < timezone.now():
                continue
            b = my.get((gc.pk, d))
            canc = cancelled.get((gc.pk, d))
            items.append({"cancelled": canc is not None, "cancel_reason": canc or "","id": gc.pk, "name": gc.name, "time": gc.start_time.strftime("%H:%M"),
                          "duration": gc.duration_min, "trainer": gc.trainer.get_full_name() if gc.trainer else "",
                          "room": gc.room, "color": gc.color, "capacity": gc.capacity, "booked": gc.booked_count(d),
                          "my_booking": {"id": b.pk, "status": b.status} if b else None,
                          "opens_in_hours": max(0, round((start - timezone.now()).total_seconds() / 3600
                                                         - gc.booking_opens_hours))})
        days.append({"date": d, "items": sorted(items, key=lambda x: x["time"])})
    return Response({"days": days})


@api_view(["POST"])
@permission_classes([IsStudent])
def class_book(request, pk):
    gc = get_object_or_404(GymClass, pk=pk, is_active=True)
    d = parse_date(str(request.data.get("date", "")))
    if not d:
        return Response({"detail": "Fecha inválida."}, status=400)
    try:
        b = book(gc, request.user.member, d)
    except BookingError as e:
        return Response({"detail": str(e)}, status=400)
    return Response({"id": b.pk, "status": b.status})


@api_view(["POST"])
@permission_classes([IsStudent])
def booking_cancel(request, pk):
    b = get_object_or_404(ClassBooking, pk=pk, member=request.user.member)
    try:
        cancel(b)
    except BookingError as e:
        return Response({"detail": str(e)}, status=400)
    return Response({"ok": True})


# ------------------------------------------------------------------ notificaciones
@api_view(["GET"])
def notifications(request):
    qs = Notification.objects.filter(user=request.user)[:50]
    return Response({"results": [{"id": n.pk, "title": n.title, "body": n.body, "url": n.url, "kind": n.kind,
                                  "is_read": n.is_read, "created_at": n.created_at} for n in qs]})


@api_view(["POST"])
def notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"ok": True})


@api_view(["POST", "DELETE"])
def push_subscribe(request):
    d = request.data
    endpoint = d.get("endpoint")
    if not endpoint:
        return Response({"detail": "Falta endpoint."}, status=400)
    if request.method == "DELETE":
        PushSubscription.objects.filter(endpoint=endpoint, user=request.user).delete()
        return Response(status=204)
    keys = d.get("keys") or {}
    PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={
        "user": request.user, "p256dh": keys.get("p256dh", ""), "auth": keys.get("auth", ""),
        "user_agent": request.headers.get("User-Agent", "")[:200]})
    return Response({"ok": True})


@api_view(["GET"])
def leaderboard(request):
    """Ranking mensual de constancia (sesiones) — motiva sin exponer datos sensibles."""
    start = timezone.localdate().replace(day=1)
    rows = (WorkoutSession.objects.filter(date__gte=start).values("member", "member__first_name",
                                                                   "member__last_name")
            .annotate(n=Count("id", distinct=True)).order_by("-n")[:20])
    me_id = getattr(getattr(request.user, "member", None), "pk", None)
    return Response({"results": [{"name": f"{r['member__first_name']} {r['member__last_name'][:1]}.",
                                  "sessions": r["n"], "me": r["member"] == me_id} for r in rows]})
