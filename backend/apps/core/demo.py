"""Datos de demostración para probar todo el sistema (python manage.py create_gym ... --demo)."""
import random
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

FIRST_M = ["Juan", "Martín", "Lucas", "Mateo", "Santiago", "Tomás", "Nicolás", "Facundo", "Agustín", "Gonzalo",
           "Federico", "Diego", "Pablo", "Ezequiel", "Franco"]
FIRST_F = ["Sofía", "Valentina", "Camila", "Lucía", "Martina", "Julieta", "Agustina", "Florencia", "Micaela",
           "Carolina", "Paula", "Rocío", "Milagros", "Belén", "Antonella"]
LAST = ["González", "Rodríguez", "Gómez", "Fernández", "López", "Díaz", "Martínez", "Pérez", "García", "Sánchez",
        "Romero", "Sosa", "Álvarez", "Torres", "Ruiz", "Ramírez", "Flores", "Benítez", "Acosta", "Medina"]


def _aware(d, h=19, m=0):
    return timezone.make_aware(datetime.combine(d, time(h, m)))


def load_demo_data(seed=7):
    from apps.accounts.models import User
    from apps.billing.models import CashSession, Expense, PaymentMethod
    from apps.billing.services import pay_charges
    from apps.body.models import BodyMeasurement
    from apps.classes.models import ClassBooking, GymClass
    from apps.core.models import GymSettings
    from apps.crm.models import Lead, LeadActivity, MessageTemplate, Task
    from apps.members.models import Member
    from apps.members.services import ensure_app_access
    from apps.memberships.models import CheckIn, Plan
    from apps.memberships.services import sell_membership
    from apps.training.models import Exercise
    from apps.training.services import save_routine, save_session

    rnd = random.Random(seed)
    today = timezone.localdate()
    cfg = GymSettings.get()
    cfg.enrollment_fee = Decimal("8000")
    cfg.save()

    owner = User.objects.filter(role=User.Role.OWNER).first()
    trainers = []
    for u, fn, ln, spec in [("profe", "Lucas", "Bianchi", "Hipertrofia, powerlifting"),
                            ("profe2", "Carla", "Méndez", "Funcional, descenso de grasa")]:
        t, created = User.objects.get_or_create(username=u, defaults={
            "first_name": fn, "last_name": ln, "role": User.Role.TRAINER, "specialties": spec,
            "email": f"{u}@demo.com"})
        if created:
            t.set_password("profe123")
            t.save()
        trainers.append(t)
    ger, created = User.objects.get_or_create(username="gerente", defaults={
        "first_name": "Pablo", "last_name": "Ríos", "role": User.Role.ADMIN})
    if created:
        ger.set_password("gerente123")
        ger.save()
    rec, created = User.objects.get_or_create(username="recepcion", defaults={
        "first_name": "Ana", "last_name": "Suárez", "role": User.Role.RECEPTION})
    if created:
        rec.set_password("recepcion123")
        rec.save()

    plans = list(Plan.objects.filter(is_active=True).exclude(period="day"))
    from apps.memberships.models import Promotion

    Promotion.objects.get_or_create(name="Verano 2x1 en matrícula", defaults={
        "kind": "free_enrollment", "description": "Arrancá sin pagar la matrícula", "ends_on": today + timedelta(days=45),
        "only_new_members": True, "color": "#f97316"})
    promo, _ = Promotion.objects.get_or_create(name="Trimestral -15%", defaults={
        "kind": "percent", "value": 15, "description": "15% off en el plan trimestral", "color": "#a855f7",
        "ends_on": today + timedelta(days=30)})
    promo.plans.set(Plan.objects.filter(period="quarter"))
    methods = list(PaymentMethod.objects.all())
    cash = PaymentMethod.objects.filter(kind="cash").first()
    CashSession.objects.get_or_create(closed_at__isnull=True, defaults={"opened_by": owner, "opening_amount": 20000})

    # ---------------------------------------------------------- socios
    members = []
    for i in range(45):
        female = i % 2 == 1
        fn = rnd.choice(FIRST_F if female else FIRST_M)
        ln = rnd.choice(LAST)
        m = Member.objects.create(
            first_name=fn, last_name=ln, dni=str(30000000 + i * 7919), email=f"socio{i}@demo.com",
            phone=f"11{rnd.randint(40000000, 69999999)}", sex="F" if female else "M",
            birth_date=today - timedelta(days=rnd.randint(18 * 365, 55 * 365)),
            height_cm=Decimal(str(rnd.randint(155, 172) if female else rnd.randint(165, 190))),
            goal=rnd.choice([g for g, _ in Member.Goal.choices]), trainer=rnd.choice(trainers),
            joined_at=today - timedelta(days=rnd.randint(5, 360)),
            medical_clearance_until=today + timedelta(days=rnd.randint(-30, 300)),
            source=rnd.choice(["Instagram", "Recomendación", "Pasaba por la puerta", "Google"]),
        )
        members.append(m)

    # alumno demo con acceso a la app
    star = members[0]
    star.first_name, star.last_name, star.dni, star.sex = "Martín", "Demo", "12345678", "M"
    star.trainer = trainers[0]
    star.goal = Member.Goal.HYPERTROPHY
    star.birth_date = today - timedelta(days=29 * 365)
    star.height_cm = Decimal("178")
    star.save()
    user, _ = ensure_app_access(star, password="alumno123")
    user.username = "alumno"
    user.must_change_password = False
    user.save()
    for m in members[1:12]:
        ensure_app_access(m)

    # ---------------------------------------------------------- membresías, pagos e ingresos
    for idx, m in enumerate(members):
        start = m.joined_at
        plan = rnd.choice(plans)
        churn_at = today - timedelta(days=rnd.randint(20, 90)) if idx % 9 == 8 else None
        first = True
        while start <= today and (not churn_at or start < churn_at):
            pay_now = rnd.random() > 0.12 or start < today - timedelta(days=40)
            mem, charges, _ = sell_membership(
                m, plan, start_date=start, user=owner, charge_enrollment=first,
                pay_method=rnd.choice(methods) if pay_now else None, auto_renew=True)
            for p in m.payments.filter(paid_at__date__gt=start):
                p.paid_at = _aware(start, rnd.randint(8, 21), rnd.randint(0, 59))
                p.save(update_fields=["paid_at"])
            # ingresos
            d = mem.start_date
            freq = rnd.choice([2, 3, 4, 5])
            while d <= min(mem.end_date, today) and (not churn_at or d < churn_at):
                if d.weekday() < 6 and rnd.random() < freq / 6:
                    CheckIn.objects.create(member=m, membership=mem, method=rnd.choice(["qr", "dni", "manual"]),
                                           created_at=_aware(d, rnd.choice([7, 8, 9, 12, 18, 19, 20, 21]),
                                                             rnd.randint(0, 59)))
                d += timedelta(days=1)
            start = mem.end_date + timedelta(days=1)
            first = False
        if idx % 13 == 5:  # algunos dejaron de venir
            m.checkins.filter(created_at__gte=timezone.now() - timedelta(days=15)).delete()

    for _ in range(12):
        Expense.objects.create(date=today - timedelta(days=rnd.randint(0, 60)), method=cash,
                               category=rnd.choice(["services", "maintenance", "marketing", "equipment"]),
                               description=rnd.choice(["Luz", "Limpieza", "Publicidad Instagram", "Discos nuevos",
                                                       "Arreglo de cinta", "Internet"]),
                               amount=Decimal(rnd.randint(8, 120) * 1000))
    # un pago parcial para ver deudas
    if members[3].charges.filter(status="pending").exists():
        pay_charges(members[3], Decimal("5000"), cash, user=rec)

    # ---------------------------------------------------------- clases
    schedule = [("Funcional", 0, 8), ("Funcional", 2, 8), ("Funcional", 4, 8), ("Spinning", 1, 19),
                ("Spinning", 3, 19), ("Cross training", 0, 20), ("Cross training", 2, 20), ("Yoga", 5, 10),
                ("GAP", 1, 9), ("GAP", 3, 9), ("Boxeo recreativo", 4, 20)]
    colors = {"Funcional": "#f97316", "Spinning": "#ef4444", "Cross training": "#8b5cf6", "Yoga": "#10b981",
              "GAP": "#ec4899", "Boxeo recreativo": "#0ea5e9"}
    classes = [GymClass.objects.create(name=n, weekday=wd, start_time=time(h, 0), capacity=rnd.choice([12, 15, 20]),
                                       trainer=rnd.choice(trainers), color=colors[n], room="Salón principal")
               for n, wd, h in schedule]
    for gc in classes:
        for d in gc.next_dates(weeks=2):
            for m in rnd.sample(members, rnd.randint(3, min(gc.capacity, 12))):
                ClassBooking.objects.get_or_create(gym_class=gc, member=m, date=d)

    # ---------------------------------------------------------- CRM
    stages = ["new", "new", "contacted", "contacted", "trial", "negotiation", "won", "lost"]
    for i in range(22):
        female = rnd.random() > 0.5
        lead = Lead.objects.create(
            name=f"{rnd.choice(FIRST_F if female else FIRST_M)} {rnd.choice(LAST)}",
            phone=f"11{rnd.randint(40000000, 69999999)}", source=rnd.choice([s for s, _ in Lead.Source.choices]),
            stage=rnd.choice(stages), interest=rnd.choice(plans), assigned_to=rnd.choice([rec, owner]),
            next_contact=today + timedelta(days=rnd.randint(-3, 7)), goal=rnd.choice(
                ["Bajar de peso", "Ganar masa muscular", "Volver a entrenar", "Preparación física"]),
            lost_reason="Precio" if i % 7 == 0 else "")
        LeadActivity.objects.create(lead=lead, kind="whatsapp", text="Consultó precios por Instagram", by=rec)
    Task.objects.create(title="Llamar a proveedores de discos", priority="normal", assigned_to=owner)
    Task.objects.create(title="Renovar seguro del gimnasio", priority="high", assigned_to=owner,
                        due_date=today + timedelta(days=3))
    MessageTemplate.objects.get_or_create(name="Recordatorio de vencimiento", defaults={
        "body": "¡Hola {nombre}! Te recordamos que tu plan {plan} vence el {vencimiento}. ¡Te esperamos en {gimnasio}! 💪"})
    MessageTemplate.objects.get_or_create(name="Te extrañamos", defaults={
        "body": "Hola {nombre}, hace unos días que no te vemos por {gimnasio}. ¿Todo bien? ¡Te esperamos para volver a entrenar!"})
    MessageTemplate.objects.get_or_create(name="Deuda pendiente", defaults={
        "body": "Hola {nombre}, tenés un saldo pendiente de {deuda}. Podés abonarlo en recepción o desde la app. ¡Gracias!"})
    MessageTemplate.objects.get_or_create(name="Promo leads", defaults={
        "body": "¡Hola {nombre}! Esta semana tenés la matrícula bonificada en {gimnasio}. ¿Querés venir a una clase de prueba?"})

    # ---------------------------------------------------------- rutina + historial de entrenamiento
    ex = {e.name: e for e in Exercise.objects.all()}

    def E(name, sets, rmin, rmax, w=None, fail=False, rest=90):
        return {"exercise": ex[name].pk, "sets": sets, "reps_min": rmin, "reps_max": rmax, "target_weight": w,
                "to_failure": fail, "rest_seconds": rest}

    payload = {
        "name": "Hipertrofia PPL", "goal": "Ganar masa muscular", "member": star.pk,
        "notes": "Calentá 10 minutos antes. Última serie de cada ejercicio al fallo técnico.",
        "start_date": (today - timedelta(days=60)).isoformat(),
        "days": [
            {"name": "Día A · Empuje", "exercises": [
                E("Press de banca plano", 4, 6, 10, 60, rest=150), E("Press inclinado con mancuernas", 3, 8, 12, 22),
                E("Press militar con barra", 3, 6, 10, 35), E("Elevaciones laterales", 3, 12, 15, 8, rest=60),
                E("Extensión de tríceps con soga", 3, 10, 15, 20, fail=True, rest=60)]},
            {"name": "Día B · Tirón", "exercises": [
                E("Dominadas", 4, 6, 10, fail=True, rest=120), E("Remo con barra", 4, 8, 10, 55),
                E("Jalón al pecho", 3, 10, 12, 50), E("Face pull", 3, 12, 15, 15, rest=60),
                E("Curl con barra", 3, 8, 12, 25, rest=60)]},
            {"name": "Día C · Piernas", "exercises": [
                E("Sentadilla con barra", 4, 6, 8, 80, rest=180), E("Peso muerto rumano", 3, 8, 10, 70, rest=120),
                E("Prensa de piernas 45°", 3, 10, 12, 140), E("Curl femoral acostado", 3, 10, 12, 35),
                E("Gemelos de pie en máquina", 4, 12, 15, 60, rest=60), E("Plancha frontal", 3, None, None)]},
        ],
    }
    routine = save_routine(payload, trainer=trainers[0])
    days = list(routine.days.prefetch_related("exercises__exercise"))
    # ~8 semanas de sesiones con progresión
    d = today - timedelta(days=56)
    k = 0
    while d < today:
        if d.weekday() in (0, 2, 4):
            day = days[k % 3]
            week = (d - (today - timedelta(days=56))).days // 7
            sets = []
            for rex in day.exercises.all():
                base = float(rex.target_weight or 0)
                for n in range(1, rex.sets + 1):
                    if rex.exercise.tracking == "time":
                        sets.append({"client_uuid": str(uuid.uuid4()), "exercise": rex.exercise_id,
                                     "routine_exercise": rex.pk, "set_number": n, "duration_seconds": 40 + week * 5})
                        continue
                    weight = (base + 2.5 * (week // 2)) if base else None
                    reps = (rex.reps_min or 8) + (week % 2) * 2 + rnd.randint(-1, 1) - (n // 3)
                    sets.append({"client_uuid": str(uuid.uuid4()), "exercise": rex.exercise_id,
                                 "routine_exercise": rex.pk, "set_number": n, "reps": max(reps, 3),
                                 "weight": weight, "to_failure": n == rex.sets and rex.to_failure,
                                 "created_at": _aware(d, 19, n).isoformat()})
            save_session(star, {"client_uuid": str(uuid.uuid4()), "routine_day": day.pk, "date": d.isoformat(),
                                "started_at": _aware(d, 19).isoformat(), "finished_at": _aware(d, 20, 10).isoformat(),
                                "feeling": rnd.randint(3, 5), "sets": sets})
            k += 1
        d += timedelta(days=1)

    # ---------------------------------------------------------- mediciones
    for w in range(0, 9, 2):
        dd = today - timedelta(days=56 - w * 7)
        BodyMeasurement.objects.create(
            member=star, date=dd, weight_kg=Decimal(str(round(82 - w * 0.35, 1))), height_cm=Decimal("178"),
            neck=Decimal("39"), shoulders=Decimal(str(118 + w * 0.3)), chest=Decimal(str(102 + w * 0.4)),
            waist=Decimal(str(round(86 - w * 0.6, 1))), abdomen=Decimal(str(round(89 - w * 0.7, 1))),
            hip=Decimal("99"), arm_right=Decimal(str(35 + w * 0.2)), arm_left=Decimal(str(34.6 + w * 0.2)),
            thigh_right=Decimal("58"), thigh_left=Decimal("57.5"), calf_right=Decimal("38"), calf_left=Decimal("38"),
            recorded_by=trainers[0])
    for m in members[1:20]:
        h = float(m.height_cm)
        weight = round((h - 100) * rnd.uniform(0.85, 1.15), 1)
        BodyMeasurement.objects.create(member=m, date=today - timedelta(days=rnd.randint(1, 40)),
                                       weight_kg=Decimal(str(weight)), height_cm=m.height_cm,
                                       neck=Decimal(str(rnd.randint(31, 41))), waist=Decimal(str(rnd.randint(66, 98))),
                                       abdomen=Decimal(str(rnd.randint(70, 102))), hip=Decimal(str(rnd.randint(90, 108))))
