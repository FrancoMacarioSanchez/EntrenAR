from django.db import transaction
from django.utils import timezone

from .models import ClassBooking, ClassCancellation


class BookingError(Exception):
    pass


@transaction.atomic
def book(gym_class, member, date):
    from apps.memberships.services import evaluate_access

    if date.weekday() != gym_class.weekday:
        raise BookingError("La clase no se dicta ese día.")
    c = gym_class.cancellation(date)
    if c:
        raise BookingError(f"La clase de ese día está suspendida{f' ({c.reason})' if c.reason else ''}.")
    start = gym_class.starts_at(date)
    now = timezone.now()
    if start < now:
        raise BookingError("La clase ya empezó.")
    if (start - now).total_seconds() > gym_class.booking_opens_hours * 3600:
        raise BookingError("Las reservas todavía no están abiertas.")
    allowed, reason, m = evaluate_access(member)
    if not allowed and "Agotó" not in reason:
        raise BookingError(reason)
    if m and not m.plan.includes_classes:
        raise BookingError("Tu plan no incluye clases grupales.")
    status = ClassBooking.Status.BOOKED
    if gym_class.booked_count(date) >= gym_class.capacity:
        status = ClassBooking.Status.WAITLIST
    b, created = ClassBooking.objects.select_for_update().get_or_create(
        gym_class=gym_class, member=member, date=date, defaults={"status": status})
    if not created and b.status == ClassBooking.Status.CANCELLED:
        b.status = status
        b.save(update_fields=["status"])
    return b


@transaction.atomic
def cancel(booking, by_staff=False):
    gc = booking.gym_class
    start = gc.starts_at(booking.date)
    if not by_staff and (start - timezone.now()).total_seconds() < gc.cancel_limit_hours * 3600:
        raise BookingError(f"Solo podés cancelar hasta {gc.cancel_limit_hours} h antes.")
    was_booked = booking.status == ClassBooking.Status.BOOKED
    booking.status = ClassBooking.Status.CANCELLED
    booking.save(update_fields=["status"])
    if was_booked:  # promover lista de espera
        nxt = (ClassBooking.objects.filter(gym_class=gc, date=booking.date, status=ClassBooking.Status.WAITLIST)
               .order_by("created_at").first())
        if nxt:
            nxt.status = ClassBooking.Status.BOOKED
            nxt.save(update_fields=["status"])
            from apps.core.notify import notify

            if nxt.member.user:
                notify(nxt.member.user, "¡Tenés lugar!", f"Se liberó un cupo en {gc.name} el {booking.date:%d/%m}.",
                       "/app/clases", kind="class")
    return booking


@transaction.atomic
def suspend_occurrence(gym_class, date, reason="", user=None):
    """Suspende la clase de una fecha y avisa a los anotados."""
    from apps.core.notify import notify

    c, created = ClassCancellation.objects.get_or_create(gym_class=gym_class, date=date,
                                                         defaults={"reason": reason, "created_by": user})
    if created:
        for b in gym_class.bookings.filter(date=date, status__in=["booked", "waitlist"]).select_related("member__user"):
            if b.member.user:
                notify(b.member.user, f"Se suspendió {gym_class.name}",
                       f"La clase del {date:%d/%m} a las {gym_class.start_time:%H:%M} no se dicta. {reason}".strip(),
                       "/app/clases", kind="class")
    return c


def restore_occurrence(gym_class, date):
    ClassCancellation.objects.filter(gym_class=gym_class, date=date).delete()


def force_add(gym_class, member, date):
    """El profe o el staff anotan a alguien aunque no cumpla las reglas de reserva."""
    b, _ = ClassBooking.objects.get_or_create(gym_class=gym_class, member=member, date=date)
    if b.status in ("cancelled", "waitlist", "no_show"):
        b.status = ClassBooking.Status.BOOKED
        b.save(update_fields=["status"])
    return b
