from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.utils import TenantPath
from apps.members.models import Member

CIRCUMFERENCES = [
    ("neck", "Cuello"), ("shoulders", "Hombros"), ("chest", "Pecho"), ("waist", "Cintura"),
    ("abdomen", "Abdomen (ombligo)"), ("hip", "Cadera"), ("arm_left", "Brazo izq."), ("arm_right", "Brazo der."),
    ("arm_flexed_left", "Brazo izq. contraído"), ("arm_flexed_right", "Brazo der. contraído"),
    ("forearm_left", "Antebrazo izq."), ("forearm_right", "Antebrazo der."), ("wrist", "Muñeca"),
    ("thigh_left", "Muslo izq."), ("thigh_right", "Muslo der."), ("calf_left", "Pantorrilla izq."),
    ("calf_right", "Pantorrilla der."),
]
SKINFOLDS = [
    ("sf_chest", "Pectoral"), ("sf_midaxillary", "Axilar medio"), ("sf_triceps", "Tríceps"),
    ("sf_subscapular", "Subescapular"), ("sf_abdominal", "Abdominal"), ("sf_suprailiac", "Suprailíaco"),
    ("sf_thigh", "Muslo"),
]


def _cm(label):
    return models.DecimalField(f"{label} (cm)", max_digits=5, decimal_places=1, null=True, blank=True)


def _mm(label):
    return models.DecimalField(f"Pliegue {label.lower()} (mm)", max_digits=5, decimal_places=1, null=True, blank=True)


class BodyMeasurement(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="measurements", verbose_name="socio")
    date = models.DateField("fecha", default=timezone.localdate)
    weight_kg = models.DecimalField("peso (kg)", max_digits=5, decimal_places=1, null=True, blank=True)
    height_cm = models.DecimalField("altura (cm)", max_digits=5, decimal_places=1, null=True, blank=True)
    bioimpedance_bf = models.DecimalField("% grasa por bioimpedancia", max_digits=4, decimal_places=1, null=True,
                                          blank=True)
    resting_hr = models.PositiveSmallIntegerField("FC en reposo", null=True, blank=True)
    notes = models.CharField("notas", max_length=250, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    # resultados calculados
    bmi = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    body_fat = models.DecimalField("% grasa", max_digits=4, decimal_places=1, null=True, blank=True)
    body_fat_method = models.CharField(max_length=16, blank=True)
    fat_mass = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    lean_mass = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    ffmi = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    results = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # perímetros (cm)
    neck = _cm("Cuello")
    shoulders = _cm("Hombros")
    chest = _cm("Pecho")
    waist = _cm("Cintura")
    abdomen = _cm("Abdomen (ombligo)")
    hip = _cm("Cadera")
    arm_left = _cm("Brazo izq.")
    arm_right = _cm("Brazo der.")
    arm_flexed_left = _cm("Brazo izq. contraído")
    arm_flexed_right = _cm("Brazo der. contraído")
    forearm_left = _cm("Antebrazo izq.")
    forearm_right = _cm("Antebrazo der.")
    wrist = _cm("Muñeca")
    thigh_left = _cm("Muslo izq.")
    thigh_right = _cm("Muslo der.")
    calf_left = _cm("Pantorrilla izq.")
    calf_right = _cm("Pantorrilla der.")
    # pliegues cutáneos (mm)
    sf_chest = _mm("Pectoral")
    sf_midaxillary = _mm("Axilar medio")
    sf_triceps = _mm("Tríceps")
    sf_subscapular = _mm("Subescapular")
    sf_abdominal = _mm("Abdominal")
    sf_suprailiac = _mm("Suprailíaco")
    sf_thigh = _mm("Muslo")

    class Meta:
        ordering = ("-date", "-id")
        verbose_name = "medición"
        verbose_name_plural = "mediciones"

    def __str__(self):
        return f"{self.member} · {self.date:%d/%m/%Y}"

    def age_at(self):
        b = self.member.birth_date
        if not b:
            return None
        return self.date.year - b.year - ((self.date.month, self.date.day) < (b.month, b.day))

    def recompute(self):
        from .composition import compute

        height = self.height_cm or self.member.height_cm
        if not self.height_cm and height:
            self.height_cm = height
        r = compute(
            sex=self.member.sex, age=self.age_at(), weight=self.weight_kg, height=height, neck=self.neck,
            waist=self.waist, abdomen=self.abdomen, hip=self.hip, bioimpedance=self.bioimpedance_bf,
            skinfolds={f[3:]: getattr(self, f) for f, _ in SKINFOLDS},
        )
        def within(v, lo, hi):  # nunca guardar un valor que no entra en la columna
            return v if v is not None and lo <= v <= hi else None

        self.results = r
        self.bmi = within(r["bmi"], 5, 99)
        self.body_fat = within(r["body_fat"], 2, 70)
        self.body_fat_method = r["method"] or ""
        self.fat_mass = within(r["fat_mass"], 0, 999)
        self.lean_mass = within(r["lean_mass"], 0, 999)
        self.ffmi = within(r["ffmi"], 5, 99)
        return r

    def save(self, *args, **kwargs):
        self.recompute()
        super().save(*args, **kwargs)
        if self.height_cm and not self.member.height_cm:
            self.member.height_cm = self.height_cm
            self.member.save(update_fields=["height_cm"])


class ProgressPhoto(models.Model):
    class Pose(models.TextChoices):
        FRONT = "front", "Frente"
        SIDE = "side", "Perfil"
        BACK = "back", "Espalda"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="photos")
    date = models.DateField(default=timezone.localdate)
    pose = models.CharField(max_length=6, choices=Pose.choices, default=Pose.FRONT)
    image = models.ImageField(upload_to=TenantPath("progress"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-date", "pose")
