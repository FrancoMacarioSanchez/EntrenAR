"""Clases grupales: grilla semanal, reservas y asistencia."""
from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.classes.models import WEEKDAYS, ClassBooking, GymClass
from apps.classes.services import BookingError, book, cancel, restore_occurrence, suspend_occurrence
from apps.members.models import Member

from .permissions import perm_required


@perm_required('classes_view')
def schedule(request):
    ref = parse_date(request.GET.get("week", "")) or timezone.localdate()
    monday = ref - timedelta(days=ref.weekday())
    classes = GymClass.objects.filter(is_active=True).select_related("trainer")
    cols = []
    for wd, label in WEEKDAYS:
        date = monday + timedelta(days=wd)
        items = []
        for gc in classes:
            if gc.weekday == wd:
                items.append({"c": gc, "booked": gc.booked_count(date), "date": date,
                              "cancelled": gc.cancellation(date)})
        cols.append({"label": label, "date": date, "items": items, "today": date == timezone.localdate()})
    return render(request, "panel/classes/schedule.html", {
        "cols": cols, "monday": monday, "prev": monday - timedelta(days=7), "next": monday + timedelta(days=7),
        "section": "clases"})


@perm_required('classes_view')
def class_day(request, pk, date):
    gc = get_object_or_404(GymClass, pk=pk)
    d = parse_date(date)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            member = Member.objects.filter(pk=request.POST.get("member")).first()
            if member:
                try:
                    book(gc, member, d)
                    messages.success(request, f"{member} anotado/a.")
                except BookingError as e:
                    b, _ = ClassBooking.objects.get_or_create(gym_class=gc, member=member, date=d)
                    b.status = ClassBooking.Status.BOOKED
                    b.save()
                    messages.warning(request, f"Anotado igual (forzado por staff): {e}")
        elif action in ("attended", "no_show", "booked"):
            b = get_object_or_404(ClassBooking, pk=request.POST.get("booking"), gym_class=gc)
            b.status = action
            b.save(update_fields=["status"])
        elif action == "cancel":
            b = get_object_or_404(ClassBooking, pk=request.POST.get("booking"), gym_class=gc)
            cancel(b, by_staff=True)
        elif action == "suspend":
            suspend_occurrence(gc, d, request.POST.get("reason", "")[:200], request.user)
            messages.success(request, "Clase suspendida. Avisamos a los anotados.")
        elif action == "restore":
            restore_occurrence(gc, d)
            messages.success(request, "La clase vuelve a estar habilitada.")
        return redirect("panel:class_day", pk=pk, date=date)
    bookings = gc.bookings.filter(date=d).select_related("member").order_by("status", "created_at")
    members = Member.objects.filter(status="active").exclude(bookings__gym_class=gc, bookings__date=d)
    return render(request, "panel/classes/day.html", {"gc": gc, "date": d, "bookings": bookings, "section": "clases",
                                                      "cancellation": gc.cancellation(d),
                                                      "members": members,
                                                      "active": bookings.filter(status__in=["booked", "attended"]).count()})


@require_POST
@perm_required('classes_view')
def class_mark_all(request, pk, date):
    gc = get_object_or_404(GymClass, pk=pk)
    gc.bookings.filter(date=parse_date(date), status="booked").update(status="attended")
    return redirect("panel:class_day", pk=pk, date=date)
