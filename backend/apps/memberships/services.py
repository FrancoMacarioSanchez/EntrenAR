"""Venta de membresías, renovaciones, congelamientos y control de acceso."""
from datetime import timedelta

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import GymSettings
from apps.core.utils import money

from .models import CheckIn, Freeze, Membership, Plan


@transaction.atomic
def sell_membership(member, plan, *, start_date=None, discount_percent=0, user=None, auto_renew=None,
                    charge_enrollment=None, pay_method=None, pay_amount=None, notes="", promotion=None):
    """Crea la membresía + cargos (cuota y matrícula) y opcionalmente registra el pago.

    `promotion` se suma al descuento manual: % se acumula (tope 100), $ se resta, días extra alargan la
    membresía y «matrícula bonificada» no cobra la matrícula.
    """
    from decimal import Decimal

    from apps.billing.models import Charge
    from apps.billing.services import pay_charges

    from .models import Promotion

    cfg = GymSettings.get()
    today = timezone.localdate()
    if start_date is None:
        last = member.memberships.exclude(status=Membership.Status.CANCELLED).order_by("-end_date").first()
        start_date = last.end_date + timedelta(days=1) if last and last.end_date >= today else today
    pct, amount, extra_days = Decimal(str(discount_percent or 0)), Decimal("0"), 0
    if promotion is not None:
        problem = promotion.problem_for(plan, member)
        if problem:
            raise ValueError(problem)
        if promotion.kind == Promotion.Kind.PERCENT:
            pct = min(pct + promotion.value, Decimal("100"))
        elif promotion.kind == Promotion.Kind.AMOUNT:
            amount = promotion.value
        elif promotion.kind == Promotion.Kind.EXTRA_DAYS:
            extra_days = int(promotion.value)
        elif promotion.kind == Promotion.Kind.FREE_ENROLLMENT:
            charge_enrollment = False
        Promotion.objects.filter(pk=promotion.pk).update(uses=models.F("uses") + 1)
        notes = f"{notes} · Promo: {promotion.name}".strip(" ·")
    m = Membership.objects.create(
        member=member, plan=plan, start_date=start_date,
        end_date=plan.end_date_from(start_date) + timedelta(days=extra_days),
        price=plan.price, discount_percent=pct, discount_amount=amount, promotion=promotion, created_by=user,
        notes=notes[:200], auto_renew=cfg.auto_renew_default if auto_renew is None else auto_renew,
    )
    charges = [Charge.objects.create(
        member=member, membership=m, kind=Charge.Kind.MEMBERSHIP, amount=m.final_price,
        concept=f"{plan.name} {start_date:%d/%m} al {m.end_date:%d/%m/%Y}", due_date=start_date,
    )]
    if charge_enrollment is None:
        charge_enrollment = cfg.enrollment_fee > 0 and member.memberships.count() == 1
    if charge_enrollment and cfg.enrollment_fee > 0:
        charges.append(Charge.objects.create(member=member, kind=Charge.Kind.ENROLLMENT, amount=cfg.enrollment_fee,
                                             concept="Matrícula", due_date=start_date))
    payments = []
    if pay_method is not None:
        total = sum(c.amount for c in charges)
        payments = pay_charges(member, money(pay_amount if pay_amount not in (None, "") else total), pay_method,
                               user=user, charges=charges)
    if member.status != member.Status.ACTIVE:
        member.status = member.Status.ACTIVE
        member.save(update_fields=["status"])
    return m, charges, payments


@transaction.atomic
def renew(membership, user=None):
    if membership.renewed_to_id:
        return membership.renewed_to
    plan = membership.plan
    if not plan.is_active:
        return None
    new, _, _ = sell_membership(membership.member, plan, start_date=membership.end_date + timedelta(days=1),
                                discount_percent=membership.discount_percent, user=user,
                                auto_renew=membership.auto_renew, charge_enrollment=False, notes="Renovación")
    membership.renewed_to = new
    membership.save(update_fields=["renewed_to"])
    return new


@transaction.atomic
def freeze(membership, start_date, end_date, reason="", user=None):
    if end_date < start_date:
        raise ValueError("La fecha de fin debe ser posterior al inicio.")
    f = Freeze.objects.create(membership=membership, start_date=start_date, end_date=end_date, reason=reason,
                              created_by=user)
    membership.end_date += timedelta(days=f.days)
    if start_date <= timezone.localdate() <= end_date:
        membership.status = Membership.Status.FROZEN
    membership.save(update_fields=["end_date", "status"])
    return f


def find_member(code):
    from apps.members.models import Member

    code = (code or "").strip()
    if not code:
        return None
    return Member.objects.filter(Q(access_code__iexact=code) | Q(dni=code)).first()


def evaluate_access(member):
    """Devuelve (permitido, motivo, membresía)."""
    from apps.billing.models import Charge

    cfg = GymSettings.get()
    today = timezone.localdate()
    if member.status == member.Status.SUSPENDED:
        return False, "Socio suspendido", None
    state, m = member.membership_state()
    if state == "none":
        return False, "No tiene membresía", None
    if state == "frozen":
        return False, "Membresía congelada", m
    if state == "expired":
        return False, f"Cuota vencida el {m.end_date:%d/%m}", m
    if m.start_date > today:
        return False, f"Su membresía empieza el {m.start_date:%d/%m}", m
    if cfg.block_access_with_debt:
        overdue = Charge.objects.filter(member=member, status__in=["pending", "partial"],
                                        due_date__lt=today - timedelta(days=cfg.access_grace_days))
        if overdue.exists():
            return False, "Tiene deuda vencida", m
    if cfg.require_medical_clearance and not member.medical_ok:
        return False, "Apto físico vencido o faltante", m
    left = m.visits_left()
    if left is not None and left <= 0:
        return False, "Agotó los ingresos de su plan", m
    if state == "grace":
        return True, f"Cuota vencida el {m.end_date:%d/%m} (tolerancia)", m
    if state == "expiring":
        return True, f"Vence en {m.remaining_days} días", m
    return True, "Acceso permitido", m


@transaction.atomic
def check_in(member, method=CheckIn.Method.MANUAL, user=None, force=False):
    allowed, reason, m = evaluate_access(member)
    if force and not allowed:
        allowed, reason = True, f"Autorizado manualmente ({reason})"
    recent = member.checkins.filter(allowed=True, created_at__gte=timezone.now() - timedelta(minutes=90)).first()
    if allowed and recent:
        return recent, True, "Ya registró su ingreso", m
    c = CheckIn.objects.create(member=member, membership=m, method=method, allowed=allowed, reason=reason, by=user)
    return c, allowed, reason, m


def plans_for_select():
    return Plan.objects.filter(is_active=True)
