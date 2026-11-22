from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.utils import TenantPath


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = "owner", "Dueño"
        ADMIN = "admin", "Gerente"
        RECEPTION = "reception", "Recepción"
        TRAINER = "trainer", "Entrenador"
        STUDENT = "student", "Alumno"

    role = models.CharField("rol", max_length=12, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField("teléfono", max_length=40, blank=True)
    avatar = models.ImageField(upload_to=TenantPath("avatars"), null=True, blank=True)
    bio = models.TextField("presentación", blank=True)
    specialties = models.CharField("especialidades", max_length=200, blank=True)
    must_change_password = models.BooleanField(default=False)
    is_support = models.BooleanField("soporte CoreX", default=False)
    custom_permissions = models.BooleanField("permisos personalizados", default=False,
                                             help_text="Si está apagado se usan los permisos estándar del rol.")
    permissions = models.JSONField("permisos", default=list, blank=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_full_name() or self.username

    def perm_codes(self):
        from .perms import ALL, PRESETS

        if self.is_superuser or self.role == self.Role.OWNER:
            return set(ALL)
        if self.custom_permissions:
            return set(self.permissions or [])
        return set(PRESETS.get(self.role, []))

    def can(self, *codes):
        """True si tiene al menos uno de los permisos."""
        if not getattr(self, "_perm_cache", None):
            self._perm_cache = self.perm_codes()
        return any(c in self._perm_cache for c in codes)

    @property
    def is_owner(self):
        return self.is_superuser or self.role == self.Role.OWNER

    @property
    def is_manager(self):
        return self.is_superuser or self.role in (self.Role.OWNER, self.Role.ADMIN)

    @property
    def is_staff_member(self):
        return self.is_manager or self.role == self.Role.RECEPTION

    @property
    def is_trainer(self):
        return self.role == self.Role.TRAINER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def initials(self):
        n = (self.first_name[:1] + self.last_name[:1]) or self.username[:2]
        return n.upper()
