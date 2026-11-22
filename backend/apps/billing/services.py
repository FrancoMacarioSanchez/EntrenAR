"""Cobros, caja, recargos, facturación (ARCA vía servicio externo) y Mercado Pago."""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditLog, GymSettings
from apps.core.utils import money

from .models import CashSession, Charge, Payment

log = logging.getLogger(__name__)


@transaction.atomic
def pay_charges(member, amount, method, *, user=None, charges=None, reference="", notes="", external_id="",
                paid_at=None):
    """Imputa un pago a los cargos pendientes (los más viejos primero). Devuelve la lista de pagos."""
    amount = money(amount)
    if amount <= 0:
        raise ValueError("El importe debe ser mayor a cero.")
    if charges is None:
        charges = list(Charge.objects.filter(member=member, status__in=["pending", "partial"]).order_by("due_date", "id"))
    session = CashSession.current()
    payments, remaining = [], amount
    for ch in charges:
        if remaining <= 0:
            break
        bal = ch.balance
        if bal <= 0:
            continue
        part = min(bal, remaining)
        payments.append(_create_payment(member, ch, part, method, user, session, reference, notes, external_id, paid_at))
        remaining -= part
    if remaining > 0:  # saldo a favor / pago sin cargo
        payments.append(_create_payment(member, None, remaining, method, user, session, reference,
                                        notes or "Pago a cuenta", external_id, paid_at))
    AuditLog.log(user, "payment", f"Pago de {member} por ${amount} ({method})")
    for p in payments:
        if p.invoice_status == Payment.InvoiceStatus.PENDING:
            transaction.on_commit(lambda pid=p.pk: request_invoice_safe(pid))
    return payments


def _create_payment(member, charge, amount, method, user, session, reference, notes, external_id, paid_at):
    cfg = GymSettings.get()
    p = Payment.objects.create(
        member=member, charge=charge, amount=amount, method=method, received_by=user, cash_session=session,
        reference=reference, notes=notes, external_id=external_id, paid_at=paid_at or timezone.now(),
        invoice_status=(Payment.InvoiceStatus.PENDING if (cfg.arca_enabled and method.is_invoiceable)
                        else Payment.InvoiceStatus.NONE),
    )
    if charge:
        charge.refresh_status()
    return p


@transaction.atomic
def void_payment(payment, user=None):
    payment.is_void = True
    payment.save(update_fields=["is_void"])
    if payment.charge:
        payment.charge.refresh_status()
    AuditLog.log(user, "payment_void", f"Anuló pago #{payment.pk} de {payment.member} (${payment.amount})")


@transaction.atomic
def add_charge(member, amount, concept, kind=Charge.Kind.OTHER, due_date=None):
    return Charge.objects.create(member=member, amount=money(amount), concept=concept, kind=kind,
                                 due_date=due_date or timezone.localdate())


def apply_late_fees():
    cfg = GymSettings.get()
    if cfg.late_fee_percent <= 0:
        return 0
    limit = timezone.localdate() - timedelta(days=cfg.late_fee_after_days)
    n = 0
    for ch in Charge.objects.filter(kind=Charge.Kind.MEMBERSHIP, status__in=["pending", "partial"],
                                    late_fee_applied=False, due_date__lt=limit):
        fee = money(ch.balance * cfg.late_fee_percent / 100)
        if fee > 0:
            Charge.objects.create(member=ch.member, membership=ch.membership, kind=Charge.Kind.LATE_FEE,
                                  amount=fee, concept=f"Recargo {cfg.late_fee_percent}% — {ch.concept}")
            n += 1
        ch.late_fee_applied = True
        ch.save(update_fields=["late_fee_applied"])
    return n


# ------------------------------------------------------------------ Facturación
def request_invoice_safe(payment_id):
    try:
        request_invoice(Payment.objects.select_related("member", "method").get(pk=payment_id))
    except Exception:  # noqa: BLE001
        log.exception("No se pudo solicitar la factura del pago %s", payment_id)


def request_invoice(payment):
    """Envía el comprobante al servicio de facturación configurado (FacturAR u otro).

    Request: POST {arca_webhook_url} con Bearer token. Respuesta esperada (cualquiera de las dos):
      200 {"status": "authorized", "number": "0001-00000123", "cae": "7412..."}
      202 {"status": "queued"}  -> queda en "sent" y el servicio puede confirmar luego.
    """
    import requests
    from django.db import connection

    cfg = GymSettings.get()
    if not (cfg.arca_enabled and cfg.arca_webhook_url):
        return payment
    m = payment.member
    body = {
        "source": "entrenar", "tenant": connection.schema_name, "payment_id": payment.pk,
        "date": timezone.localtime(payment.paid_at).date().isoformat(), "amount": str(payment.amount),
        "invoice_type": cfg.arca_invoice_type, "point_of_sale": cfg.arca_point_of_sale,
        "concept": payment.charge.concept if payment.charge else (payment.notes or "Servicios de gimnasio"),
        "service": True, "payment_method": payment.method.name,
        "customer": {"name": m.full_name, "doc_type": "DNI" if m.dni else "CF", "doc_number": m.dni or "",
                     "email": m.email, "address": m.address},
    }
    headers = {"Content-Type": "application/json"}
    if cfg.arca_webhook_token:
        headers["Authorization"] = f"Bearer {cfg.arca_webhook_token}"
    try:
        r = requests.post(cfg.arca_webhook_url, json=body, headers=headers, timeout=20)
        data = r.json() if r.content else {}
        payment.invoice_response = data
        if r.status_code >= 400:
            payment.invoice_status = Payment.InvoiceStatus.ERROR
        elif data.get("status") == "authorized":
            payment.invoice_status = Payment.InvoiceStatus.AUTHORIZED
            payment.invoice_number = data.get("number", "")
            payment.invoice_cae = data.get("cae", "")
        else:
            payment.invoice_status = Payment.InvoiceStatus.SENT
    except Exception as exc:  # noqa: BLE001
        payment.invoice_status = Payment.InvoiceStatus.ERROR
        payment.invoice_response = {"error": str(exc)}
    payment.save(update_fields=["invoice_status", "invoice_number", "invoice_cae", "invoice_response"])
    return payment


# ------------------------------------------------------------------ Mercado Pago
MP_API = "https://api.mercadopago.com"


def mp_enabled():
    return bool(GymSettings.get().mp_access_token)


def mp_create_link(charge, request):
    """Crea (o reutiliza) un link de pago de Checkout Pro para un cargo."""
    import requests

    cfg = GymSettings.get()
    if not cfg.mp_access_token:
        raise ValueError("Mercado Pago no está configurado.")
    if charge.mp_init_point and charge.status != Charge.Status.PAID:
        return charge.mp_init_point
    base = request.build_absolute_uri("/")
    pref = {
        "items": [{"title": charge.concept[:250], "quantity": 1, "currency_id": "ARS",
                   "unit_price": float(charge.balance)}],
        "payer": {"name": charge.member.first_name, "surname": charge.member.last_name,
                  "email": charge.member.email or None},
        "external_reference": f"charge:{charge.pk}",
        "notification_url": f"{base}webhooks/mercadopago/",
        "back_urls": {"success": f"{base}app/membresia?pago=ok", "failure": f"{base}app/membresia?pago=error",
                      "pending": f"{base}app/membresia?pago=pendiente"},
        "auto_return": "approved",
    }
    r = requests.post(f"{MP_API}/checkout/preferences", json=pref, timeout=20,
                      headers={"Authorization": f"Bearer {cfg.mp_access_token}"})
    r.raise_for_status()
    data = r.json()
    charge.mp_preference_id = data.get("id", "")
    charge.mp_init_point = data.get("init_point", "")
    charge.save(update_fields=["mp_preference_id", "mp_init_point"])
    return charge.mp_init_point


def mp_process_payment(mp_payment_id):
    """Consulta el pago en MP y, si está aprobado, lo registra (idempotente por external_id)."""
    import requests

    from .models import PaymentMethod

    cfg = GymSettings.get()
    if not cfg.mp_access_token or not mp_payment_id:
        return None
    if Payment.objects.filter(external_id=f"mp:{mp_payment_id}").exists():
        return None
    r = requests.get(f"{MP_API}/v1/payments/{mp_payment_id}", timeout=20,
                     headers={"Authorization": f"Bearer {cfg.mp_access_token}"})
    r.raise_for_status()
    data = r.json()
    ref = data.get("external_reference") or ""
    if data.get("status") != "approved" or not ref.startswith("charge:"):
        return None
    charge = Charge.objects.filter(pk=ref.split(":", 1)[1]).select_related("member").first()
    if not charge:
        return None
    method = (PaymentMethod.objects.filter(kind="mercadopago", is_active=True).first()
              or PaymentMethod.objects.create(name="Mercado Pago", kind="mercadopago"))
    amount = Decimal(str(data.get("transaction_amount", charge.balance)))
    pays = pay_charges(charge.member, amount, method, charges=[charge], reference=f"MP {mp_payment_id}",
                       external_id=f"mp:{mp_payment_id}")
    from apps.core.notify import notify

    if charge.member.user:
        notify(charge.member.user, "¡Pago acreditado!", f"Recibimos tu pago de ${amount}.", "/app/membresia",
               kind="payment")
    return pays
