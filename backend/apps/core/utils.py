import os
import secrets
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.db import connection
from django.utils.deconstruct import deconstructible


@deconstructible
class TenantPath:
    """upload_to que separa los archivos por gimnasio: <schema>/<carpeta>/<uuid>.<ext>"""

    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()[:8] or ".jpg"
        return f"{connection.schema_name}/{self.folder}/{uuid.uuid4().hex}{ext}"

    def __eq__(self, other):
        return isinstance(other, TenantPath) and other.folder == self.folder


def money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt_money(value):
    v = money(value)
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if s.endswith(",00"):
        s = s[:-3]
    return f"$ {s}"


def wa_link(phone, text=""):
    from urllib.parse import quote

    digits = "".join(c for c in (phone or "") if c.isdigit())
    if not digits:
        return ""
    if not digits.startswith("54"):
        digits = "549" + digits.lstrip("0")
    return f"https://wa.me/{digits}?text={quote(text)}" if text else f"https://wa.me/{digits}"


def new_checkin_key():
    return secrets.token_urlsafe(18)
