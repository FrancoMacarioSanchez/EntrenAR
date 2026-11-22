"""Validación de mediciones: rangos razonables y mensajes claros (en lugar de errores de base de datos)."""
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import CIRCUMFERENCES, SKINFOLDS

LABELS = dict(CIRCUMFERENCES + SKINFOLDS + [("weight_kg", "Peso"), ("height_cm", "Altura"),
                                            ("bioimpedance_bf", "% grasa por bioimpedancia"),
                                            ("resting_hr", "Frecuencia cardíaca en reposo")])
RANGES = {"weight_kg": (20, 350, "kg"), "height_cm": (100, 240, "cm"), "bioimpedance_bf": (3, 70, "%"),
          "resting_hr": (25, 220, "lpm"), "neck": (20, 70, "cm"), "wrist": (10, 30, "cm")}
for f, _ in CIRCUMFERENCES:
    RANGES.setdefault(f, (10, 250, "cm"))
for f, _ in SKINFOLDS:
    RANGES[f] = (2, 90, "mm")


class MeasurementError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(" · ".join(errors.values()))


def to_decimal(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        raise ValueError("no es un número") from None


def clean_measurement(payload):
    """Devuelve (fecha, {campo: valor}) o lanza MeasurementError con un mensaje por campo."""
    errors, out = {}, {}
    for f, (lo, hi, unit) in RANGES.items():
        try:
            v = to_decimal(payload.get(f))
        except ValueError:
            errors[f] = f"{LABELS[f]}: no es un número válido."
            continue
        if v is None:
            continue
        if f == "height_cm" and Decimal("1") <= v <= Decimal("2.5"):
            v = v * 100  # la cargaron en metros
        if not (lo <= v <= hi):
            errors[f] = f"{LABELS[f]}: {v:g} {unit} está fuera de rango ({lo} a {hi} {unit})."
            continue
        out[f] = int(v) if f == "resting_hr" else v.quantize(Decimal("0.1"))
    if not out and not errors:
        errors["__all__"] = "Cargá al menos una medida."
    date = parse_date(str(payload.get("date") or "")) or timezone.localdate()
    if date > timezone.localdate():
        errors["date"] = "La fecha no puede ser futura."
    if errors:
        raise MeasurementError(errors)
    return date, out
