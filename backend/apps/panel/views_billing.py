"""Cobros, pagos, caja y comprobantes."""
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.billing.models import CashSession, Charge, Payment, PaymentMethod
from apps.billing.services import mp_create_link, pay_charges, request_invoice, void_payment
from apps.core.models import AuditLog
from apps.core.utils import fmt_money, wa_link
from apps.members.models import Member

from .forms import CashCloseForm, CashOpenForm, PaymentForm
from .permissions import perm_required


@perm_required('collect')
def collect(request, member_id):
    """Cobrar a un socio: imputa a los cargos elegidos o a los más viejos."""
    member = get_object_or_404(Member, pk=member_id)
    pending = list(Charge.objects.filter(member=member, status__in=["pending", "partial"]).order_by("due_date"))
    total = sum((c.balance for c in pending), 0)
    form = PaymentForm(request.POST or None, initial={"amount": total or None})
    if request.method == "POST" and form.is_valid():
        ids = request.POST.getlist("charges")
        selected = [c for c in pending if str(c.pk) in ids] or None
        d = form.cleaned_data
        payments = pay_charges(member, d["amount"], d["method"], user=request.user, charges=selected,
                               reference=d["reference"], notes=d["notes"])
        messages.success(request, f"Pago de {fmt_money(d['amount'])} registrado.")
        return redirect("panel:receipt", pk=payments[0].pk)
    return render(request, "panel/billing/collect.html", {
        "member": member, "pending": pending, "total": total, "form": form, "section": "recepcion",
        "cash_open": CashSession.current() is not None})


@perm_required('collect')
def debts(request):
    today = timezone.localdate()
    qs = Charge.objects.filter(status__in=["pending", "partial"]).select_related("member").order_by("due_date")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(member__first_name__icontains=q) | Q(member__last_name__icontains=q) | Q(member__dni=q))
    if request.GET.get("overdue"):
        qs = qs.filter(due_date__lt=today)
    by_member = {}
    for c in qs:
        e = by_member.setdefault(c.member_id, {"member": c.member, "charges": [], "total": 0, "oldest": c.due_date})
        e["charges"].append(c)
        e["total"] += c.balance
    rows = sorted(by_member.values(), key=lambda e: e["oldest"])
    for r in rows:
        r["wa"] = wa_link(r["member"].phone, f"Hola {r['member'].first_name}, te recordamos que tenés un saldo "
                                             f"pendiente de {fmt_money(r['total'])}. ¡Gracias!")
        r["overdue"] = r["oldest"] < today
    return render(request, "panel/billing/debts.html", {
        "rows": rows, "grand_total": sum(r["total"] for r in rows), "q": q, "section": "finanzas", "today": today})


@perm_required('payments_list')
def payments(request):
    qs = Payment.objects.select_related("member", "method", "charge", "received_by")
    today = timezone.localdate()
    d_from = parse_date(request.GET.get("from", "")) or today.replace(day=1)
    d_to = parse_date(request.GET.get("to", "")) or today
    qs = qs.filter(paid_at__date__gte=d_from, paid_at__date__lte=d_to)
    if request.GET.get("method"):
        qs = qs.filter(method_id=request.GET["method"])
    if request.GET.get("invoice"):
        qs = qs.filter(invoice_status=request.GET["invoice"])
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(member__first_name__icontains=q) | Q(member__last_name__icontains=q) | Q(member__dni=q)
                       | Q(reference__icontains=q))
    total = qs.filter(is_void=False).aggregate(s=Sum("amount"))["s"] or 0
    page = Paginator(qs, 40).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "panel/billing/payments.html", {
        "page": page, "total": total, "d_from": d_from, "d_to": d_to, "q": q, "querystring": params.urlencode(),
        "methods": PaymentMethod.objects.all(), "invoice_choices": Payment.InvoiceStatus.choices, "section": "finanzas"})


@require_POST
@perm_required('void_payments')
def payment_void(request, pk):
    p = get_object_or_404(Payment, pk=pk)
    void_payment(p, user=request.user)
    messages.success(request, "Pago anulado.")
    return redirect(request.POST.get("next") or "panel:payments")


@require_POST
@perm_required('collect', 'payments_list')
def payment_invoice(request, pk):
    p = get_object_or_404(Payment, pk=pk)
    if p.invoice_status in ("none", "error", "pending"):
        p.invoice_status = Payment.InvoiceStatus.PENDING
        p.save(update_fields=["invoice_status"])
        request_invoice(p)
        messages.info(request, f"Facturación: {p.get_invoice_status_display()}")
    return redirect(request.POST.get("next") or "panel:payments")


@perm_required('collect', 'payments_list')
def receipt(request, pk):
    p = get_object_or_404(Payment.objects.select_related("member", "method", "charge", "received_by"), pk=pk)
    siblings = Payment.objects.filter(member=p.member, paid_at__gte=p.paid_at - timedelta(seconds=5),
                                      paid_at__lte=p.paid_at + timedelta(seconds=5), is_void=False)
    return render(request, "panel/billing/receipt.html", {
        "p": p, "items": siblings, "total": siblings.aggregate(s=Sum("amount"))["s"] or 0})


@require_POST
@perm_required('collect')
def charge_mp_link(request, pk):
    ch = get_object_or_404(Charge, pk=pk)
    try:
        url = mp_create_link(ch, request)
        text = f"Hola {ch.member.first_name}, te paso el link para abonar {ch.concept}: {url}"
        messages.success(request, f"Link de pago generado: {url}")
        wa = wa_link(ch.member.phone, text)
        if wa:
            return redirect(wa)
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"No se pudo generar el link de Mercado Pago: {exc}")
    return redirect(f"/socios/{ch.member_id}/?tab=cobros")


@require_POST
@perm_required('void_payments')
def charge_cancel(request, pk):
    ch = get_object_or_404(Charge, pk=pk)
    ch.status = Charge.Status.CANCELLED
    ch.save(update_fields=["status"])
    AuditLog.log(request.user, "charge_cancel", f"Anuló el cargo {ch}")
    messages.success(request, "Cargo anulado.")
    return redirect(f"/socios/{ch.member_id}/?tab=cobros")


# ------------------------------------------------------------------ caja
@perm_required('cash')
def cash(request):
    session = CashSession.current()
    posted = request.POST if request.method == "POST" else None
    open_form = CashOpenForm(posted if not session else None)
    close_form = CashCloseForm(posted if session else None)
    if request.method == "POST":
        if not session and open_form.is_valid():
            CashSession.objects.create(opened_by=request.user, **open_form.cleaned_data)
            AuditLog.log(request.user, "cash_open", "Abrió la caja")
            messages.success(request, "Caja abierta.")
            return redirect("panel:cash")
        if session and close_form.is_valid():
            session.closing_amount = close_form.cleaned_data["closing_amount"]
            session.notes = close_form.cleaned_data["notes"]
            session.closed_at = timezone.now()
            session.closed_by = request.user
            session.save()
            t = session.totals()
            AuditLog.log(request.user, "cash_close", f"Cerró la caja. Diferencia: {t['difference']}")
            if not request.user.can("cash_totals"):
                messages.success(request, "Caja cerrada. ¡Gracias!")
                return redirect("panel:cash")
            messages.success(request, f"Caja cerrada. Diferencia: {fmt_money(t['difference'])}")
            return redirect("panel:cash_detail", pk=session.pk)
    history = CashSession.objects.filter(closed_at__isnull=False).select_related("opened_by", "closed_by")[:30]
    ctx = {"session": session, "open_form": open_form, "close_form": close_form, "history": history,
           "section": "finanzas"}
    if session and request.user.can("cash_totals"):
        ctx["t"] = session.totals()
        ctx["movements"] = session.payments.select_related("member", "method").order_by("-paid_at")[:100]
        ctx["expenses"] = session.expenses.select_related("method")
    return render(request, "panel/billing/cash.html", ctx)


@perm_required('cash_totals')
def cash_detail(request, pk):
    s = get_object_or_404(CashSession, pk=pk)
    return render(request, "panel/billing/cash_detail.html", {
        "s": s, "t": s.totals(), "movements": s.payments.select_related("member", "method"),
        "expenses": s.expenses.select_related("method"), "section": "finanzas"})
