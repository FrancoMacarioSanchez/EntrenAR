"""Metas diarias: gasto calórico con Mifflin-St Jeor y reparto de macros según el objetivo."""

ACTIVITY_FACTOR = {"sedentario": 1.2, "ligero": 1.375, "moderado": 1.55, "alto": 1.725, "atleta": 1.9}
# Ajuste sobre el gasto total según objetivo y ritmo.
GOAL_ADJUST = {
    "cut": {"suave": -0.10, "moderado": -0.20, "agresivo": -0.25},
    "maintain": {"suave": 0, "moderado": 0, "agresivo": 0},
    "bulk": {"suave": 0.05, "moderado": 0.10, "agresivo": 0.15},
}
# Proteína en g por kg (rango habitual 1,6–2,2 g/kg en personas que entrenan fuerza).
PROTEIN_PER_KG = {"cut": 2.2, "maintain": 1.8, "bulk": 2.0}
FAT_SHARE = 0.25          # 25 % de las calorías
FAT_MIN_PER_KG = 0.6
KCAL_FLOOR = {"M": 1500, "F": 1200}


def bmr_mifflin(sex, weight_kg, height_cm, age):
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex == "M" else base - 161


def compute(sex, weight_kg, height_cm, age, activity="moderado", goal="maintain", pace="moderado", body_fat=None):
    """Devuelve dict con bmr, tdee, kcal, protein, carbs, fat (enteros)."""
    weight_kg, height_cm, age = float(weight_kg), float(height_cm), int(age)
    bmr = bmr_mifflin(sex, weight_kg, height_cm, age)
    tdee = bmr * ACTIVITY_FACTOR.get(activity, 1.55)
    kcal = tdee * (1 + GOAL_ADJUST.get(goal, GOAL_ADJUST["maintain"]).get(pace, 0))
    kcal = max(kcal, KCAL_FLOOR.get(sex, 1200))
    kcal = int(round(kcal / 10) * 10)

    # Con mucha grasa corporal, la proteína se calcula sobre un peso «de referencia» (masa magra / 0,8).
    ref_weight = weight_kg
    if body_fat is not None:
        high = 25 if sex == "M" else 32
        if float(body_fat) > high:
            ref_weight = weight_kg * (1 - float(body_fat) / 100) / 0.8
    protein = round(ref_weight * PROTEIN_PER_KG.get(goal, 1.8))
    fat = round(max(kcal * FAT_SHARE / 9, weight_kg * FAT_MIN_PER_KG))
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    return {"bmr": round(bmr), "tdee": round(tdee), "kcal": kcal, "protein": protein, "carbs": carbs, "fat": fat}
