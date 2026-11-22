"""Estimaciones de composición corporal (todas en sistema métrico).

Fórmulas:
* US Navy (Hodgdon & Beckett, versión métrica).
* Deurenberg 1991 (IMC, edad, sexo).
* CUN-BAE (Gómez-Ambrosi 2012, validada en población hispana).
* YMCA (cintura y peso).
* Jackson-Pollock 3 y 7 pliegues + ecuación de Siri.
* FFMI normalizado (Kouri 1995).
Son ESTIMACIONES: se muestran con su método y nunca como diagnóstico.
"""
from math import log10

KG_TO_LB = 2.2046226
CM_TO_IN = 0.3937008


def _f(v):
    return float(v) if v not in (None, "") else None


def bmi(weight, height):
    if not weight or not height:
        return None
    m = height / 100
    return weight / (m * m)


def navy(sex, height, neck, waist, hip=None, abdomen=None):
    try:
        if sex == "M":
            w = abdomen or waist
            if not (w and neck and height) or w <= neck:
                return None
            return 495 / (1.0324 - 0.19077 * log10(w - neck) + 0.15456 * log10(height)) - 450
        if not (waist and hip and neck and height) or waist + hip <= neck:
            return None
        return 495 / (1.29579 - 0.35004 * log10(waist + hip - neck) + 0.22100 * log10(height)) - 450
    except (ValueError, ZeroDivisionError):
        return None


def deurenberg(b, age, sex):
    if b is None or age is None:
        return None
    return 1.20 * b + 0.23 * age - 10.8 * (1 if sex == "M" else 0) - 5.4


def cun_bae(b, age, sex):
    if b is None or age is None:
        return None
    s = 0 if sex == "M" else 1
    return (-44.988 + 0.503 * age + 10.689 * s + 3.172 * b - 0.026 * b ** 2 + 0.181 * b * s
            - 0.02 * b * age - 0.005 * b ** 2 * s + 0.00021 * b ** 2 * age)


def ymca(sex, weight, waist):
    if not weight or not waist:
        return None
    w_lb, waist_in = weight * KG_TO_LB, waist * CM_TO_IN
    k = -98.42 if sex == "M" else -76.76
    return (k + 4.15 * waist_in - 0.082 * w_lb) / w_lb * 100


def siri(density):
    return 495 / density - 450


def jp3(sex, age, chest=None, abdominal=None, thigh=None, triceps=None, suprailiac=None):
    if age is None:
        return None
    if sex == "M":
        if None in (chest, abdominal, thigh):
            return None
        s = chest + abdominal + thigh
        bd = 1.10938 - 0.0008267 * s + 0.0000016 * s ** 2 - 0.0002574 * age
    else:
        if None in (triceps, suprailiac, thigh):
            return None
        s = triceps + suprailiac + thigh
        bd = 1.0994921 - 0.0009929 * s + 0.0000023 * s ** 2 - 0.0001392 * age
    return siri(bd)


def jp7(sex, age, chest, midaxillary, triceps, subscapular, abdominal, suprailiac, thigh):
    vals = (chest, midaxillary, triceps, subscapular, abdominal, suprailiac, thigh)
    if age is None or None in vals:
        return None
    s = sum(vals)
    if sex == "M":
        bd = 1.112 - 0.00043499 * s + 0.00000055 * s ** 2 - 0.00028826 * age
    else:
        bd = 1.097 - 0.00046971 * s + 0.00000056 * s ** 2 - 0.00012828 * age
    return siri(bd)


def classify(bf, sex):
    """Rangos de referencia del American Council on Exercise."""
    if bf is None:
        return ""
    ranges = ([(6, "Grasa esencial"), (14, "Atlético"), (18, "Fitness"), (25, "Promedio"), (999, "Elevado")]
              if sex == "M" else
              [(14, "Grasa esencial"), (21, "Atlético"), (25, "Fitness"), (32, "Promedio"), (999, "Elevado")])
    for limit, label in ranges:
        if bf < limit:
            return label
    return ""


def clamp(v):
    if v is None:
        return None
    if v < 2 or v > 70:
        return None
    return round(v, 1)


def compute(*, sex, age, weight, height, neck=None, waist=None, abdomen=None, hip=None, skinfolds=None,
            bioimpedance=None):
    sf = {k: _f(v) for k, v in (skinfolds or {}).items()}
    weight, height = _f(weight), _f(height)
    neck, waist, abdomen, hip = _f(neck), _f(waist), _f(abdomen), _f(hip)
    b = bmi(weight, height)
    methods = {
        "jp7": clamp(jp7(sex, age, sf.get("chest"), sf.get("midaxillary"), sf.get("triceps"), sf.get("subscapular"),
                         sf.get("abdominal"), sf.get("suprailiac"), sf.get("thigh"))),
        "jp3": clamp(jp3(sex, age, chest=sf.get("chest"), abdominal=sf.get("abdominal"), thigh=sf.get("thigh"),
                         triceps=sf.get("triceps"), suprailiac=sf.get("suprailiac"))),
        "navy": clamp(navy(sex, height, neck, waist, hip, abdomen)),
        "ymca": clamp(ymca(sex, weight, abdomen or waist)),
        "cun_bae": clamp(cun_bae(b, age, sex)),
        "deurenberg": clamp(deurenberg(b, age, sex)),
    }
    bio = clamp(_f(bioimpedance))
    order = ["jp7", "jp3", "navy", "cun_bae", "deurenberg", "ymca"]
    chosen = ("bioimpedance", bio) if bio else next(((k, methods[k]) for k in order if methods[k] is not None),
                                                     (None, None))
    method, bf = chosen
    out = {"bmi": round(b, 1) if b else None, "methods": methods, "body_fat": bf, "method": method,
           "classification": classify(bf, sex), "fat_mass": None, "lean_mass": None, "ffmi": None,
           "whr": None, "whtr": None}
    if bf is not None and weight:
        fat = weight * bf / 100
        lean = weight - fat
        out.update(fat_mass=round(fat, 1), lean_mass=round(lean, 1))
        if height:
            hm = height / 100
            out["ffmi"] = round(lean / hm ** 2 + 6.1 * (1.8 - hm), 1)
    w = waist or abdomen
    if w and hip:
        out["whr"] = round(w / hip, 2)
    if w and height:
        out["whtr"] = round(w / height, 2)
    return out
