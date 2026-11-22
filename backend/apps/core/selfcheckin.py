"""Autoingreso: QR fijo (impreso) o QR rotativo (pantalla en la entrada, cambia cada 30 s)."""
import hashlib
import hmac
import math
import time

WINDOW = 30


def _sig(key, window):
    return hmac.new(key.encode(), f"entrenar-checkin:{window}".encode(), hashlib.sha256).hexdigest()[:12]


def rotating_token(key, now=None):
    w = int((now or time.time()) // WINDOW)
    return f"r{w}.{_sig(key, w)}"


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para que se lea bien


def static_code(key):
    """Código corto de 6 caracteres impreso en el cartel (para escribirlo si la cámara no funciona)."""
    n = int(hmac.new(key.encode(), b"entrenar-short", hashlib.sha256).hexdigest(), 16)
    out = ""
    for _ in range(6):
        n, r = divmod(n, len(ALPHABET))
        out += ALPHABET[r]
    return out


def rotating_pin(key, now=None):
    w = int((now or time.time()) // WINDOW)
    return _pin(key, w)


def _pin(key, w):
    return f"{int(hmac.new(key.encode(), f'entrenar-pin:{w}'.encode(), hashlib.sha256).hexdigest(), 16) % 1000000:06d}"


def verify(key, value):
    """Devuelve 'static', 'rotating' o None. Acepta el QR, la URL completa o los códigos cortos."""
    value = (value or "").strip()
    if not value or not key:
        return None
    if "k=" in value:  # pegaron la URL completa
        from urllib.parse import parse_qs, urlparse

        value = (parse_qs(urlparse(value).query).get("k") or [value])[0]
    if hmac.compare_digest(value, key):
        return "static"
    norm = value.upper().replace(" ", "").replace("-", "")
    if len(norm) == 6 and hmac.compare_digest(norm, static_code(key)):
        return "static"
    if len(norm) == 6 and norm.isdigit():
        now_w = int(time.time() // WINDOW)
        if any(hmac.compare_digest(norm, _pin(key, w)) for w in range(now_w - 2, now_w + 1)):
            return "rotating"
    if value.startswith("r") and "." in value:
        w_str, sig = value[1:].split(".", 1)
        if not w_str.isdigit():
            return None
        w, now_w = int(w_str), int(time.time() // WINDOW)
        if now_w - 2 <= w <= now_w and hmac.compare_digest(sig, _sig(key, w)):
            return "rotating"
    return None


def distance_m(lat1, lng1, lat2, lng2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
