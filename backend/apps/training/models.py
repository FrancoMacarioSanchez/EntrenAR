import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.utils import TenantPath
from apps.members.models import Member


class Exercise(models.Model):
    class Muscle(models.TextChoices):
        CHEST = "chest", "Pecho"
        BACK = "back", "Espalda"
        SHOULDERS = "shoulders", "Hombros"
        BICEPS = "biceps", "Bíceps"
        TRICEPS = "triceps", "Tríceps"
        FOREARMS = "forearms", "Antebrazos"
        QUADS = "quads", "Cuádriceps"
        HAMSTRINGS = "hamstrings", "Isquiotibiales"
        GLUTES = "glutes", "Glúteos"
        CALVES = "calves", "Gemelos"
        CORE = "core", "Abdomen / core"
        FULL_BODY = "full_body", "Cuerpo completo"
        CARDIO = "cardio", "Cardio"

    class Equipment(models.TextChoices):
        BARBELL = "barbell", "Barra"
        DUMBBELL = "dumbbell", "Mancuernas"
        MACHINE = "machine", "Máquina"
        CABLE = "cable", "Polea"
        BODYWEIGHT = "bodyweight", "Peso corporal"
        KETTLEBELL = "kettlebell", "Kettlebell"
        BAND = "band", "Banda elástica"
        SMITH = "smith", "Smith"
        OTHER = "other", "Otro"

    class Tracking(models.TextChoices):
        WEIGHT_REPS = "weight_reps", "Peso y repeticiones"
        REPS = "reps", "Solo repeticiones"
        TIME = "time", "Tiempo"
        DISTANCE_TIME = "distance_time", "Distancia y tiempo"

    name = models.CharField("nombre", max_length=100, unique=True)
    muscle_group = models.CharField("grupo muscular", max_length=12, choices=Muscle.choices)
    secondary_muscles = models.CharField("músculos secundarios", max_length=150, blank=True)
    equipment = models.CharField("equipamiento", max_length=12, choices=Equipment.choices, default=Equipment.OTHER)
    tracking = models.CharField("se registra por", max_length=14, choices=Tracking.choices,
                                default=Tracking.WEIGHT_REPS)
    instructions = models.TextField("técnica / indicaciones", blank=True)
    video_url = models.URLField("video", blank=True)
    image = models.ImageField("imagen", upload_to=TenantPath("exercises"), null=True, blank=True)
    is_active = models.BooleanField("activo", default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ("muscle_group", "name")
        verbose_name = "ejercicio"
        verbose_name_plural = "ejercicios"

    def __str__(self):
        return self.name


class Routine(models.Model):
    member = models.ForeignKey(Member, null=True, blank=True, on_delete=models.CASCADE, related_name="routines",
                               verbose_name="alumno")
    trainer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="routines_created", verbose_name="entrenador")
    name = models.CharField("nombre", max_length=100)
    goal = models.CharField("objetivo", max_length=120, blank=True)
    notes = models.TextField("indicaciones generales", blank=True)
    start_date = models.DateField("desde", default=timezone.localdate)
    end_date = models.DateField("hasta", null=True, blank=True)
    is_active = models.BooleanField("activa", default=True)
    is_template = models.BooleanField("es plantilla", default=False)
    version = models.PositiveSmallIntegerField(default=1)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="versions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_active", "-start_date", "-id")
        verbose_name = "rutina"
        verbose_name_plural = "rutinas"

    def __str__(self):
        return self.name


class RoutineDay(models.Model):
    routine = models.ForeignKey(Routine, on_delete=models.CASCADE, related_name="days")
    name = models.CharField("nombre", max_length=60)
    order = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField("notas", max_length=200, blank=True)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return f"{self.routine} · {self.name}"


class RoutineExercise(models.Model):
    day = models.ForeignKey(RoutineDay, on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="+")
    order = models.PositiveSmallIntegerField(default=0)
    sets = models.PositiveSmallIntegerField("series", default=3)
    reps_min = models.PositiveSmallIntegerField("reps (mín.)", null=True, blank=True)
    reps_max = models.PositiveSmallIntegerField("reps (máx.)", null=True, blank=True)
    to_failure = models.BooleanField("al fallo", default=False)
    target_weight = models.DecimalField("peso sugerido (kg)", max_digits=6, decimal_places=2, null=True, blank=True)
    duration_seconds = models.PositiveIntegerField("duración (s)", null=True, blank=True)
    rest_seconds = models.PositiveSmallIntegerField("descanso (s)", default=90)
    tempo = models.CharField(max_length=12, blank=True, help_text="Ej: 3-1-1-0")
    rpe_target = models.DecimalField("RPE objetivo", max_digits=3, decimal_places=1, null=True, blank=True)
    superset_group = models.CharField("superserie", max_length=2, blank=True, help_text="Misma letra = superserie")
    notes = models.CharField("notas", max_length=250, blank=True)

    class Meta:
        ordering = ("order", "id")

    @property
    def reps_label(self):
        if self.to_failure and not self.reps_min:
            return "Al fallo"
        if self.reps_min and self.reps_max and self.reps_max != self.reps_min:
            r = f"{self.reps_min}-{self.reps_max}"
        else:
            r = str(self.reps_min or self.reps_max or "")
        return f"{r} (al fallo)" if self.to_failure else r


class WorkoutSession(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="sessions")
    routine_day = models.ForeignKey(RoutineDay, null=True, blank=True, on_delete=models.SET_NULL, related_name="sessions")
    date = models.DateField(default=timezone.localdate, db_index=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    feeling = models.PositiveSmallIntegerField("sensación (1-5)", null=True, blank=True)
    notes = models.TextField(blank=True)
    trainer_feedback = models.TextField(blank=True)
    feedback_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta:
        ordering = ("-date", "-started_at")

    @property
    def volume(self):
        return sum(float(s.weight or 0) * (s.reps or 0) for s in self.sets.all() if not s.is_warmup)

    @property
    def duration_min(self):
        if not self.finished_at:
            return None
        return int((self.finished_at - self.started_at).total_seconds() // 60)


class SetLog(models.Model):
    session = models.ForeignKey(WorkoutSession, on_delete=models.CASCADE, related_name="sets")
    routine_exercise = models.ForeignKey(RoutineExercise, null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="logs")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="logs")
    set_number = models.PositiveSmallIntegerField(default=1)
    reps = models.PositiveSmallIntegerField(null=True, blank=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    to_failure = models.BooleanField(default=False)
    rpe = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    is_warmup = models.BooleanField(default=False)
    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("created_at", "set_number")

    @property
    def e1rm(self):
        """1RM estimado (Epley). Solo tiene sentido hasta ~12 reps."""
        if not self.weight or not self.reps:
            return 0.0
        w, r = float(self.weight), int(self.reps)
        return w if r == 1 else round(w * (1 + r / 30), 1)


class PersonalRecord(models.Model):
    class Kind(models.TextChoices):
        E1RM = "e1rm", "1RM estimado"
        MAX_WEIGHT = "max_weight", "Peso máximo"
        REPS_AT_WEIGHT = "reps_at_weight", "Más repeticiones con el mismo peso"
        MAX_REPS = "max_reps", "Más repeticiones (peso corporal)"
        VOLUME = "volume", "Mayor volumen en una serie"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="records")
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="records")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    value = models.DecimalField(max_digits=8, decimal_places=2)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    reps = models.PositiveSmallIntegerField(null=True, blank=True)
    previous_value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    set_log = models.ForeignKey(SetLog, null=True, blank=True, on_delete=models.SET_NULL, related_name="records")
    achieved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-achieved_at",)

    @property
    def label(self):
        k = self.Kind
        if self.kind == k.E1RM:
            return f"1RM estimado {self.value:g} kg"
        if self.kind == k.MAX_WEIGHT:
            return f"Peso máximo {self.weight:g} kg × {self.reps}"
        if self.kind == k.REPS_AT_WEIGHT:
            return f"{self.reps} reps con {self.weight:g} kg"
        if self.kind == k.MAX_REPS:
            return f"{self.reps} repeticiones"
        return f"Volumen {self.value:g} kg"


class Achievement(models.Model):
    """Logros/insignias (constancia, récords, hitos)."""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="achievements")
    code = models.CharField(max_length=40)
    title = models.CharField(max_length=100)
    description = models.CharField(max_length=200, blank=True)
    icon = models.CharField(max_length=8, default="🏆")
    achieved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-achieved_at",)
        constraints = [models.UniqueConstraint(fields=["member", "code"], name="uniq_achievement")]
