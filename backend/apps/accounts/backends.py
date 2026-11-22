from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.db import connection
from django.db.models import Q

from .models import User


class FlexibleLoginBackend(ModelBackend):
    """Permite ingresar con usuario, email o DNI."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        ident = username.strip()
        q = Q(username__iexact=ident) | Q(email__iexact=ident)
        if connection.schema_name != settings.PUBLIC_SCHEMA_NAME:
            q |= Q(member__dni=ident)
        for user in User.objects.filter(q).distinct()[:3]:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        User().set_password(password)  # mitiga timing attacks
        return None
