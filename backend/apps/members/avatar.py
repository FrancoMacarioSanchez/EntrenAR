"""Configuración del avatar 3D (morph targets).

El cliente genera una malla base y 13 shape keys; acá se guarda solo la CONFIGURACIÓN (versionada) y se
calculan los pesos con las mismas fórmulas que `frontend/src/body3d/morph/targets.js`, para que cualquier
cliente (panel, app, un modelo GLB externo) muestre el mismo cuerpo.
"""
import re

SCHEMA_VERSION = 2

OPTIONS = {
    "sex": ["M", "F"],
    "hair_style": ["shaved", "short", "curly", "long", "ponytail", "bun", "bald"],
    "top_style": ["tank", "tee", "sports", "none"],
    "bottom_style": ["shorts", "leggings", "joggers"],
}
COLOR_KEYS = ["hair_color", "top_color", "bottom_color", "shoe_color"]
SKIN_TONES = 6

REGIONS = ["neck", "shoulders", "chest", "waist", "abdomen", "hip", "arm", "forearm", "thigh", "calf"]
MORPH_TARGETS = ["sex_female", "muscle", "fat"] + [f"girth_{r}" for r in REGIONS]
REGION_STEP = 0.4
SCULPT_LIMIT = 1.0  # moldeado manual: suma hasta ±1 al peso girth_<región> (±40% de perímetro)
BASE_MUSCLE, BASE_FAT = 0.5, 0.3

# perímetros de referencia (cm): mismo valor que REF en avatarSpec.js
REF = {
    "M": {"neck": 38, "shoulders": 116, "chest": 100, "waist": 84, "abdomen": 88, "hip": 98, "arm": 33, "forearm": 28,
          "thigh": 56, "calf": 37},
    "F": {"neck": 32, "shoulders": 102, "chest": 90, "waist": 70, "abdomen": 80, "hip": 98, "arm": 28, "forearm": 24,
          "thigh": 55, "calf": 35},
}
MEASURE_FIELDS = {
    "neck": ["neck"], "shoulders": ["shoulders"], "chest": ["chest"], "waist": ["waist"], "abdomen": ["abdomen"],
    "hip": ["hip"], "arm": ["arm_right", "arm_left"], "forearm": ["forearm_right", "forearm_left"],
    "thigh": ["thigh_right", "thigh_left"], "calf": ["calf_right", "calf_left"],
}
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def defaults(sex="M"):
    f = sex == "F"
    return {
        "v": SCHEMA_VERSION, "sex": sex, "skin": 1, "hair_style": "ponytail" if f else "short", "hair_color": "#3f2a1d",
        "top_style": "sports" if f else "tank", "top_color": "#ff5a1f", "bottom_style": "leggings" if f else "shorts",
        "bottom_color": "#111827", "shoe_color": "#f5f5f4", "muscle": 0.5, "fat": 0.3, "use_measures": True,
        "sculpt": {},
    }


def clean_sculpt(data):
    out = {}
    if not isinstance(data, dict):
        return out
    for r in REGIONS:
        try:
            v = round(min(max(float(data.get(r, 0) or 0), -SCULPT_LIMIT), SCULPT_LIMIT), 2)
        except (TypeError, ValueError):
            continue
        if v:
            out[r] = v
    return out


def clean(data, sex="M"):
    """Valida y completa una configuración. Ignora claves desconocidas o inválidas."""
    data = data if isinstance(data, dict) else {}
    out = defaults(data.get("sex") if data.get("sex") in OPTIONS["sex"] else sex)
    for k, allowed in OPTIONS.items():
        if data.get(k) in allowed:
            out[k] = data[k]
    for k in COLOR_KEYS:
        if isinstance(data.get(k), str) and HEX.fullmatch(data[k]):
            out[k] = data[k].lower()
    for k in ("muscle", "fat"):
        try:
            out[k] = min(max(float(data.get(k, out[k])), 0.0), 1.0)
        except (TypeError, ValueError):
            pass
    try:
        out["skin"] = min(max(int(data.get("skin", out["skin"])), 0), SKIN_TONES - 1)
    except (TypeError, ValueError):
        pass
    if "use_measures" in data:
        out["use_measures"] = bool(data["use_measures"])
    out["sculpt"] = clean_sculpt(data.get("sculpt"))
    if out["sex"] == "F" and out["top_style"] == "none":
        out["top_style"] = "sports"
    out["v"] = SCHEMA_VERSION
    return out


def girth_factors(avatar, measurement=None):
    ref = REF.get(avatar.get("sex"), REF["M"])
    f = {}
    for region, fields in MEASURE_FIELDS.items():
        vals = []
        if measurement is not None and avatar.get("use_measures", True):
            for name in fields:
                v = getattr(measurement, name, None) if not isinstance(measurement, dict) else measurement.get(name)
                if v not in (None, "") and float(v) > 5:
                    vals.append(float(v))
        f[region] = min(max(sum(vals) / len(vals) / ref[region], 0.72), 1.55) if vals else 1.0
    if f["waist"] != 1 and f["abdomen"] == 1:
        f["abdomen"] = f["waist"]
    if f["abdomen"] != 1 and f["waist"] == 1:
        f["waist"] = 1 + (f["abdomen"] - 1) * 0.8
    return f


def morph_weights(avatar, measurement=None):
    a = clean(avatar)
    f = girth_factors(a, measurement)
    w = {"sex_female": 1.0 if a["sex"] == "F" else 0.0,
         "muscle": (a["muscle"] - BASE_MUSCLE) / (1 - BASE_MUSCLE),
         "fat": (a["fat"] - BASE_FAT) / (1 - BASE_FAT)}
    for r in REGIONS:
        w[f"girth_{r}"] = round((f[r] - 1) / REGION_STEP + a["sculpt"].get(r, 0), 4)
    return {k: round(v, 4) for k, v in w.items()}


def schema():
    return {"version": SCHEMA_VERSION, "options": OPTIONS, "colors": COLOR_KEYS, "skin_tones": SKIN_TONES,
            "morph_targets": MORPH_TARGETS, "region_step": REGION_STEP,
            "sculpt": {"regions": REGIONS, "limit": SCULPT_LIMIT}, "reference_cm": REF,
            "defaults": {"M": defaults("M"), "F": defaults("F")}}
