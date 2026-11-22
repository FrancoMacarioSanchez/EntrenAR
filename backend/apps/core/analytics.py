"""Tablero de gerencia: KPIs de negocio, retención, cobranza, operación y equipo."""
import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def month_end(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def pct(a, b, digits=1):
    return round(float(a) / float(b) * 100, digits) if b else None


def f(v):
    return float(v or 0)


MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def label(d):
    return f"{MONTHS_ES[d.month - 1]} {str(d.year)[2:]}"


def active_member_ids(day):
    from apps.memberships.models import Membership

    return set(Membership.objects.filter(start_date__lte=day, end_date__gte=day).exclude(status="cancelled")
               .values_list("member_id", flat=True))


def monthly_equivalent(m):
    """Precio mensualizado de una membresía (para el MRR)."""
    days = max((m.end_date - m.start_date).days + 1, 1)
    return float(m.final_price) * 30 / days


def management_data(months=12):
    from apps.accounts.models import User
    from apps.billing.models import Charge, Expense, Payment
    from apps.classes.models import ClassBooking, GymClass
    from apps.crm.models import Lead
    from apps.members.models import Member
    from apps.memberships.models import CheckIn, Membership
    from apps.training.models import PersonalRecord, Routine, WorkoutSession

    today = timezone.localdate()
    cur = month_start(today)
    first = add_months(cur, -(months - 1))
    pays = Payment.objects.filter(is_void=False)

    # ---------------------------------------------------------------- series mensuales
    series = []
    prev_active = None
    for i in range(months):
        ms = add_months(first, i)
        me = min(month_end(ms), today)
        rev = f(pays.filter(paid_at__date__gte=ms, paid_at__date__lte=me).aggregate(s=Sum("amount"))["s"])
        exp = f(Expense.objects.filter(date__gte=ms, date__lte=me).aggregate(s=Sum("amount"))["s"])
        active = active_member_ids(me)
        new = Member.objects.filter(joined_at__gte=ms, joined_at__lte=me).count()
        lost = len(prev_active - active) if prev_active is not None else None
        visits = CheckIn.objects.filter(allowed=True, created_at__date__gte=ms, created_at__date__lte=me).count()
        series.append({"label": label(ms), "revenue": rev, "expenses": exp, "net": rev - exp, "active": len(active),
                       "new": new, "lost": lost, "visits": visits,
                       "churn": pct(lost, len(prev_active)) if prev_active else None})
        prev_active = active

    # ---------------------------------------------------------------- base actual
    active_ids = active_member_ids(today)
    n_active = len(active_ids)
    current_ms = list(Membership.objects.filter(start_date__lte=today, end_date__gte=today)
                      .exclude(status="cancelled").select_related("plan", "member"))
    mrr = sum(monthly_equivalent(m) for m in current_ms)
    arpu = mrr / n_active if n_active else 0
    last_full = [s for s in series[:-1] if s["churn"] is not None]
    churn_avg = sum(s["churn"] for s in last_full[-3:]) / len(last_full[-3:]) if last_full else None
    ltv = arpu / (churn_avg / 100) if churn_avg else None
    tenure_days = [(today - m.joined_at).days for m in Member.objects.filter(pk__in=active_ids).only("joined_at")]
    avg_tenure = sum(tenure_days) / len(tenure_days) / 30 if tenure_days else 0

    # renovación: membresías que terminaron en los últimos 30 días y tienen una posterior
    ended = Membership.objects.filter(end_date__gte=today - timedelta(days=30), end_date__lt=today).exclude(
        status="cancelled")
    renewed = sum(1 for m in ended if m.renewed_to_id or Membership.objects.filter(
        member_id=m.member_id, start_date__gt=m.end_date - timedelta(days=1)).exclude(pk=m.pk).exists())
    renewal_rate = pct(renewed, ended.count())

    # ---------------------------------------------------------------- dinero del mes
    rev_month = series[-1]["revenue"]
    rev_prev = series[-2]["revenue"] if len(series) > 1 else 0
    exp_month = series[-1]["expenses"]
    due_month = Charge.objects.filter(due_date__gte=cur, due_date__lte=today).exclude(status="cancelled")
    due_total = f(due_month.aggregate(s=Sum("amount"))["s"])
    due_paid = sum(f(c.paid_amount) for c in due_month)
    collection_rate = pct(due_paid, due_total)

    open_charges = list(Charge.objects.filter(status__in=["pending", "partial"]).select_related("member"))
    aging = {"Al día": 0.0, "1 a 30 días": 0.0, "31 a 60 días": 0.0, "61 a 90 días": 0.0, "Más de 90 días": 0.0}
    debtors = set()
    for c in open_charges:
        bal = f(c.balance)
        late = (today - c.due_date).days
        key = ("Al día" if late <= 0 else "1 a 30 días" if late <= 30 else "31 a 60 días" if late <= 60
               else "61 a 90 días" if late <= 90 else "Más de 90 días")
        aging[key] += bal
        if late > 0:
            debtors.add(c.member_id)
    debt_total = sum(aging.values())

    upcoming = Membership.objects.filter(end_date__gte=today, end_date__lte=today + timedelta(days=30),
                                         auto_renew=True, renewed_to__isnull=True).exclude(status="cancelled")
    forecast = f(sum((m.plan.price for m in upcoming.select_related("plan")), Decimal("0"))) + sum(
        f(c.balance) for c in open_charges if today <= c.due_date <= today + timedelta(days=30))

    month_pays = pays.filter(paid_at__date__gte=cur)
    by_method = [{"label": r["method__name"], "value": f(r["t"])} for r in
                 month_pays.values("method__name").annotate(t=Sum("amount")).order_by("-t")]
    cash_total = f(month_pays.filter(method__kind="cash").aggregate(s=Sum("amount"))["s"])
    by_plan = [{"label": r["plan__name"], "value": r["c"], "color": r["plan__color"]} for r in
               Membership.objects.filter(start_date__lte=today, end_date__gte=today).exclude(status="cancelled")
               .values("plan__name", "plan__color").annotate(c=Count("id")).order_by("-c")]
    exp_cat = defaultdict(float)
    for e in Expense.objects.filter(date__gte=cur):
        exp_cat[e.get_category_display()] += f(e.amount)

    # ---------------------------------------------------------------- estados de los socios
    states = Counter()
    for m in Member.objects.exclude(status="inactive").prefetch_related("memberships"):
        st, _ = m.membership_state()
        states[st] += 1
    state_labels = {"active": "Al día", "expiring": "Por vencer", "grace": "En tolerancia", "expired": "Vencidos",
                    "frozen": "Congelados", "none": "Sin plan"}
    member_states = [{"label": state_labels[k], "value": states.get(k, 0)} for k in state_labels]

    # demografía de activos
    sexes = Counter()
    ages = Counter()
    buckets = [(0, 17, "<18"), (18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 54, "45-54"),
               (55, 200, "55+")]
    for m in Member.objects.filter(pk__in=active_ids):
        sexes["Mujeres" if m.sex == "F" else "Hombres"] += 1
        a = m.age
        if a is not None:
            ages[next(lbl for lo, hi, lbl in buckets if lo <= a <= hi)] += 1
    age_dist = [{"label": lbl, "value": ages.get(lbl, 0)} for _, _, lbl in buckets]

    # ---------------------------------------------------------------- uso y engagement
    since30 = today - timedelta(days=30)
    visits30 = CheckIn.objects.filter(allowed=True, created_at__date__gte=since30, member_id__in=active_ids)
    visits_per_member = visits30.count() / n_active if n_active else 0
    visit_counts = Counter(visits30.values_list("member_id", flat=True))
    freq = {"0 visitas": 0, "1-4": 0, "5-8": 0, "9-12": 0, "13+": 0}
    for mid in active_ids:
        n = visit_counts.get(mid, 0)
        freq["0 visitas" if n == 0 else "1-4" if n <= 4 else "5-8" if n <= 8 else "9-12" if n <= 12 else "13+"] += 1
    at_risk = sum(1 for mid in active_ids if visit_counts.get(mid, 0) == 0)

    weekday = [0] * 7
    for d in visits30.values_list("created_at", flat=True):
        weekday[timezone.localtime(d).weekday()] += 1

    app_users = Member.objects.filter(pk__in=active_ids, user__isnull=False).count()
    app_active = WorkoutSession.objects.filter(date__gte=since30, member_id__in=active_ids).values(
        "member").distinct().count()
    with_routine = Routine.objects.filter(is_active=True, member_id__in=active_ids).values("member").distinct().count()

    # ---------------------------------------------------------------- CRM
    since90 = today - timedelta(days=90)
    leads = Lead.objects.filter(created_at__date__gte=since90)
    total_leads = leads.count()
    funnel = [
        {"label": "Leads", "value": total_leads},
        {"label": "Contactados", "value": leads.exclude(stage="new").count()},
        {"label": "Clase de prueba", "value": leads.filter(stage__in=["trial", "negotiation", "won"]).count()},
        {"label": "Socios", "value": leads.filter(stage="won").count()},
    ]
    src_labels = dict(Lead.Source.choices)
    sources = [{"label": src_labels.get(r["source"], r["source"]), "value": r["c"], "won": r["won"],
                "rate": pct(r["won"], r["c"], 0)} for r in
               leads.values("source").annotate(c=Count("id"), won=Count("id", filter=Q(stage="won"))).order_by("-c")]

    # ---------------------------------------------------------------- clases
    occ = []
    no_show = ClassBooking.objects.filter(date__gte=since30, date__lt=today)
    for gc in GymClass.objects.filter(is_active=True).select_related("trainer"):
        bk = gc.bookings.filter(date__gte=since30, date__lt=today)
        dates = {b.date for b in bk}
        if not dates:
            continue
        used = bk.filter(status__in=["attended", "booked", "no_show"]).count()
        occ.append({"label": f"{gc.name} {gc.get_weekday_display()[:3]} {gc.start_time:%H:%M}",
                    "value": pct(used, gc.capacity * len(dates), 0) or 0})
    occ.sort(key=lambda x: -x["value"])
    ns_total = no_show.filter(status__in=["attended", "no_show"]).count()
    no_show_rate = pct(no_show.filter(status="no_show").count(), ns_total)

    # ---------------------------------------------------------------- equipo
    trainers = []
    for t in User.objects.filter(role="trainer", is_active=True):
        st_ids = list(t.students.filter(pk__in=active_ids).values_list("pk", flat=True))
        trainers.append({
            "name": t.get_full_name() or t.username, "students": len(st_ids),
            "with_routine": Routine.objects.filter(is_active=True, member_id__in=st_ids).values("member").distinct().count(),
            "sessions": WorkoutSession.objects.filter(member_id__in=st_ids, date__gte=since30).count(),
            "prs": PersonalRecord.objects.filter(member_id__in=st_ids, achieved_at__date__gte=since30).count(),
            "routines_made": Routine.objects.filter(trainer=t, created_at__date__gte=since30).count(),
        })
    for t in trainers:
        t["coverage"] = pct(t["with_routine"], t["students"], 0)

    # ---------------------------------------------------------------- cohortes (retención por mes de alta)
    cohorts = []
    for i in range(5, -1, -1):
        cs = add_months(cur, -i)
        ids = set(Member.objects.filter(joined_at__gte=cs, joined_at__lte=month_end(cs)).values_list("pk", flat=True))
        if not ids:
            continue
        row = {"label": label(cs), "size": len(ids), "cells": []}
        for k in range(0, 6):
            point = add_months(cs, k)
            if point > cur:
                break
            day = min(month_end(point), today)
            row["cells"].append(pct(len(ids & active_member_ids(day)), len(ids), 0))
        cohorts.append(row)

    return {
        "kpis": {
            "active": n_active, "active_delta": n_active - series[-2]["active"] if len(series) > 1 else 0,
            "mrr": mrr, "arpu": arpu, "ltv": ltv, "churn": churn_avg, "retention": 100 - churn_avg if churn_avg else None,
            "renewal_rate": renewal_rate, "avg_tenure": avg_tenure,
            "revenue": rev_month, "revenue_prev": rev_prev, "revenue_delta": pct(rev_month - rev_prev, rev_prev),
            "expenses": exp_month, "net": rev_month - exp_month, "margin": pct(rev_month - exp_month, rev_month),
            "collection_rate": collection_rate, "debt": debt_total, "debtors": len(debtors), "forecast": forecast,
            "cash_share": pct(cash_total, rev_month), "visits_per_member": visits_per_member, "at_risk": at_risk,
            "app_adoption": pct(app_users, n_active, 0), "app_active": pct(app_active, n_active, 0),
            "routine_coverage": pct(with_routine, n_active, 0), "no_show": no_show_rate,
            "new_month": series[-1]["new"], "lost_month": series[-1]["lost"],
            "leads": total_leads, "conversion": pct(funnel[-1]["value"], total_leads, 0),
        },
        "series": series, "aging": [{"label": k, "value": v} for k, v in aging.items()],
        "by_method": by_method, "by_plan": by_plan,
        "expenses_by_cat": [{"label": k, "value": v} for k, v in sorted(exp_cat.items(), key=lambda x: -x[1])],
        "member_states": member_states, "sexes": [{"label": k, "value": v} for k, v in sexes.items()],
        "ages": age_dist, "frequency": [{"label": k, "value": v} for k, v in freq.items()],
        "weekday": [{"label": d, "value": weekday[i]} for i, d in enumerate(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"])],
        "funnel": funnel, "sources": sources, "occupancy": occ[:12], "trainers": trainers, "cohorts": cohorts,
    }
