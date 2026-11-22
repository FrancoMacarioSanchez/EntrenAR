from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.members.models import Member

WEEKDAYS = [(0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"), (4, "Viernes"), (5, "Sábado"),
            (6, "Domingo")]


class GymClass(models.Model):
    name = models.CharField("actividad", max_length=80)
    description = models.CharField("descripción", max_length=250, blank=True)
    trainer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="classes", limit_choices_to={"role__in": ["trainer", "owner", "admin"]},
                                verbose_name="profesor")
    weekday = models.PositiveSmallIntegerField("día", choices=WEEKDAYS)
    start_time = models.TimeField("hora")
    duration_min = models.PositiveSmallIntegerField("duración (min)", default=60)
    capacity = models.PositiveSmallIntegerField("cupo", default=20)
    room = models.CharField("sala", max_length=60, blank=True)
    color = models.CharField(max_length=9, default="#3b82f6")
    booking_opens_hours = models.PositiveSmallIntegerField("reservas abren (horas antes)", default=72)
    cancel_limit_hours = models.PositiveSmallIntegerField("cancelar hasta (horas antes)", default=2)
    is_active = models.BooleanField("activa", default=True)

    class Meta:
        ordering = ("weekday", "start_time")
        verbose_name = "clase"
        verbose_name_plural = "clases"

    def __str__(self):
        return f"{self.name} · {self.get_weekday_display()} {self.start_time:%H:%M}"

    def next_dates(self, weeks=2, from_date=None):
        d = from_date or timezone.localdate()
        first = d + timedelta(days=(self.weekday - d.weekday()) % 7)
        return [first + timedelta(weeks=i) for i in range(weeks)]

    def starts_at(self, date):
        return timezone.make_aware(datetime.combine(date, self.start_time))

    def booked_count(self, date):
        return self.bookings.filter(date=date, status__in=["booked", "attended"]).count()

    def cancellation(self, date):
        return self.cancellations.filter(date=date).first()


class ClassCancellation(models.Model):
    """Una fecha puntual en la que la clase no se dicta (feriado, profe enfermo, etc.)."""
    gym_class = models.ForeignKey(GymClass, on_delete=models.CASCADE, related_name="cancellations")
    date = models.DateField()
    reason = models.CharField("motivo", max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["gym_class", "date"], name="uniq_class_cancellation")]


class ClassBooking(models.Model):
    class Status(models.TextChoices):
        BOOKED = "booked", "Reservada"
        CANCELLED = "cancelled", "Cancelada"
        ATTENDED = "attended", "Asistió"
        NO_SHOW = "no_show", "Ausente"
        WAITLIST = "waitlist", "Lista de espera"

    gym_class = models.ForeignKey(GymClass, on_delete=models.CASCADE, related_name="bookings")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="bookings")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BOOKED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("date", "gym_class__start_time")
        constraints = [models.UniqueConstraint(fields=["gym_class", "member", "date"], name="uniq_booking")]
