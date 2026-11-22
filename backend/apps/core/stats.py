"""Métricas del gimnasio (dashboard y API del Hub)."""
from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay, TruncMonth
from django.utils import timezone


def tenant_stats(d_from, d_to):
    from apps.accounts.models import User
    from apps.billing.models import Payment
    from apps.crm.models import Lead
    from apps.crm.services import active_members
    from apps.members.models import Member
    from apps.memberships.models import CheckIn, Membership
    from apps.training.models import WorkoutSession

    pays = Payment.objects.filter(is_void=False, paid_at__date__gte=d_from, paid_at__date__lte=d_to)
    last_pay = Payment.objects.filter(is_void=False).order_by("-paid_at").first()
    last_ci = CheckIn.objects.filter(allowed=True).order_by("-created_at").first()
    return {
        "members_total": Member.objects.count(),
        "members_active": active_members().count(),
        "staff_users": User.objects.exclude(role=User.Role.STUDENT).filter(is_active=True, is_support=False).count(),
        "app_users": User.objects.filter(role=User.Role.STUDENT, is_active=True).count(),
        "memberships_sold": Membership.objects.filter(created_at__date__gte=d_from, created_at__date__lte=d_to).count(),
        "revenue": str(pays.aggregate(s=Sum("amount"))["s"] or 0),
        "revenue_by_method": {r["method__name"]: str(r["t"]) for r in pays.values("method__name").annotate(t=Sum("amount"))},
        "checkins": CheckIn.objects.filter(allowed=True, created_at__date__gte=d_from, created_at__date__lte=d_to).count(),
        "workouts_logged": WorkoutSession.objects.filter(date__gte=d_from, date__lte=d_to).count(),
        "leads_new": Lead.objects.filter(created_at__date__gte=d_from, created_at__date__lte=d_to).count(),
        "leads_won": Lead.objects.filter(stage="won", updated_at__date__gte=d_from, updated_at__date__lte=d_to).count(),
        "last_payment_at": last_pay.paid_at if last_pay else None,
        "last_checkin_at": last_ci.created_at if last_ci else None,
    }


def dashboard_data():
    from apps.billing.models import Charge, Expense, Payment
    from apps.crm.models import Lead, Task
    from apps.crm.services import active_members, segment_members
    from apps.members.models import Member
    from apps.memberships.models import CheckIn, Membership
    from apps.training.models import PersonalRecord, WorkoutSession

    today = timezone.localdate()
    month_start = today.replace(day=1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    pays = Payment.objects.filter(is_void=False)

    def revenue(a, b):
        return pays.filter(paid_at__date__gte=a, paid_at__date__lte=b).aggregate(s=Sum("amount"))["s"] or 0

    rev_month = revenue(month_start, today)
    rev_prev = revenue(prev_month_start, prev_month_start + (today - month_start))
    exp_month = Expense.objects.filter(date__gte=month_start).aggregate(s=Sum("amount"))["s"] or 0
    debt = sum((c.balance for c in Charge.objects.filter(status__in=["pending", "partial"], due_date__lt=today)), 0)
    active = active_members().count()

    # serie de 12 meses
    start12 = (month_start - timedelta(days=330)).replace(day=1)
    by_month = {r["m"].date() if hasattr(r["m"], "date") else r["m"]: float(r["t"]) for r in
                pays.filter(paid_at__date__gte=start12).annotate(m=TruncMonth("paid_at")).values("m")
                .annotate(t=Sum("amount"))}
    months, d = [], start12
    while d <= month_start:
        months.append({"label": d.strftime("%m/%y"), "value": by_month.get(d, 0), "d": d})
        d = (d + timedelta(days=32)).replace(day=1)

    new_by_month = {r["m"].date() if hasattr(r["m"], "date") else r["m"]: r["c"] for r in
                    Member.objects.filter(joined_at__gte=start12).annotate(m=TruncMonth("joined_at")).values("m")
                    .annotate(c=Count("id"))}
    growth = [{"label": m["label"], "value": new_by_month.get(m["d"], 0)} for m in months]

    # mapa de calor de ingresos (últimos 60 días) día x hora
    heat = [[0] * 24 for _ in range(7)]
    for r in (CheckIn.objects.filter(allowed=True, created_at__date__gte=today - timedelta(days=60))
              .annotate(h=ExtractHour("created_at"), wd=ExtractIsoWeekDay("created_at")).values("h", "wd")
              .annotate(c=Count("id"))):
        heat[r["wd"] - 1][r["h"]] = r["c"]

    plan_mix = list(Membership.objects.filter(start_date__lte=today, end_date__gte=today)
                    .exclude(status="cancelled").values("plan__name", "plan__color").annotate(c=Count("id"))
                    .order_by("-c"))
    leads_open = Lead.objects.exclude(stage__in=["won", "lost"]).count()
    won_90 = Lead.objects.filter(stage="won", updated_at__date__gte=today - timedelta(days=90)).count()
    closed_90 = Lead.objects.filter(stage__in=["won", "lost"], updated_at__date__gte=today - timedelta(days=90)).count()

    expired_last_month = Membership.objects.filter(end_date__gte=prev_month_start, end_date__lte=prev_month_end,
                                                   renewed_to__isnull=True).exclude(status="cancelled")
    churned = sum(1 for m in expired_last_month if not m.member.memberships.filter(start_date__gt=m.end_date).exists())
    base = Membership.objects.filter(start_date__lte=prev_month_end, end_date__gte=prev_month_start).values(
        "member").distinct().count() or 1

    return {
        "active_members": active,
        "revenue_month": rev_month,
        "revenue_prev": rev_prev,
        "revenue_delta": round((float(rev_month) - float(rev_prev)) / float(rev_prev) * 100, 1) if rev_prev else None,
        "expenses_month": exp_month,
        "net_month": float(rev_month) - float(exp_month),
        "debt_total": debt,
        "checkins_today": CheckIn.objects.filter(allowed=True, created_at__date=today).count(),
        "in_gym_now": CheckIn.objects.filter(allowed=True, created_at__gte=timezone.now() - timedelta(minutes=90)).count(),
        "expiring": segment_members("expiring").count(),
        "inactive": segment_members("inactive").count(),
        "leads_open": leads_open,
        "conversion": round(won_90 / closed_90 * 100) if closed_90 else None,
        "churn_rate": round(churned / base * 100, 1),
        "arpu": round(float(rev_month) / active) if active else 0,
        "workouts_week": WorkoutSession.objects.filter(date__gte=today - timedelta(days=7)).count(),
        "prs_week": PersonalRecord.objects.filter(achieved_at__date__gte=today - timedelta(days=7)).count(),
        "tasks_today": Task.objects.filter(done=False, due_date__lte=today).count(),
        "revenue_series": months,
        "growth_series": growth,
        "heatmap": heat,
        "plan_mix": plan_mix,
        "recent_payments": pays.select_related("member", "method")[:8],
        "recent_checkins": CheckIn.objects.select_related("member")[:8],
        "recent_prs": PersonalRecord.objects.select_related("member", "exercise")[:6],
    }
