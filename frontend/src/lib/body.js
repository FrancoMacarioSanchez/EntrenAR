// Mismas fórmulas que el backend (apps/body/composition.py) para mostrar el resultado al instante.
const log10 = Math.log10;
const num = (v) => (v === "" || v === null || v === undefined || isNaN(+v) ? null : +v);
const clamp = (v) => (v == null || !isFinite(v) || v < 2 || v > 70 ? null : Math.round(v * 10) / 10);

export function bmi(w, h) { return w && h ? w / ((h / 100) ** 2) : null; }

export function navy(sex, h, neck, waist, hip, abdomen) {
  if (sex === "M") {
    const w = abdomen || waist;
    if (!(w && neck && h) || w <= neck) return null;
    return 495 / (1.0324 - 0.19077 * log10(w - neck) + 0.15456 * log10(h)) - 450;
  }
  if (!(waist && hip && neck && h) || waist + hip <= neck) return null;
  return 495 / (1.29579 - 0.35004 * log10(waist + hip - neck) + 0.221 * log10(h)) - 450;
}
export function deurenberg(b, age, sex) { return b == null || age == null ? null : 1.2 * b + 0.23 * age - 10.8 * (sex === "M" ? 1 : 0) - 5.4; }
export function cunBae(b, age, sex) {
  if (b == null || age == null) return null;
  const s = sex === "M" ? 0 : 1;
  return -44.988 + 0.503 * age + 10.689 * s + 3.172 * b - 0.026 * b * b + 0.181 * b * s - 0.02 * b * age
    - 0.005 * b * b * s + 0.00021 * b * b * age;
}
export function ymca(sex, w, waist) {
  if (!w || !waist) return null;
  const lb = w * 2.2046226, inch = waist * 0.3937008;
  return ((sex === "M" ? -98.42 : -76.76) + 4.15 * inch - 0.082 * lb) / lb * 100;
}
const siri = (bd) => 495 / bd - 450;
export function jp3(sex, age, sf) {
  if (age == null) return null;
  if (sex === "M") {
    if ([sf.chest, sf.abdominal, sf.thigh].some((x) => x == null)) return null;
    const s = sf.chest + sf.abdominal + sf.thigh;
    return siri(1.10938 - 0.0008267 * s + 0.0000016 * s * s - 0.0002574 * age);
  }
  if ([sf.triceps, sf.suprailiac, sf.thigh].some((x) => x == null)) return null;
  const s = sf.triceps + sf.suprailiac + sf.thigh;
  return siri(1.0994921 - 0.0009929 * s + 0.0000023 * s * s - 0.0001392 * age);
}
export function jp7(sex, age, sf) {
  const v = [sf.chest, sf.midaxillary, sf.triceps, sf.subscapular, sf.abdominal, sf.suprailiac, sf.thigh];
  if (age == null || v.some((x) => x == null)) return null;
  const s = v.reduce((a, b) => a + b, 0);
  const bd = sex === "M" ? 1.112 - 0.00043499 * s + 0.00000055 * s * s - 0.00028826 * age
    : 1.097 - 0.00046971 * s + 0.00000056 * s * s - 0.00012828 * age;
  return siri(bd);
}

export const METHOD_LABELS = {
  jp7: "Jackson-Pollock 7 pliegues", jp3: "Jackson-Pollock 3 pliegues", navy: "US Navy",
  ymca: "YMCA", cun_bae: "CUN-BAE", deurenberg: "Deurenberg (IMC)", bioimpedance: "Bioimpedancia",
};

export function classify(bf, sex) {
  if (bf == null) return "";
  const r = sex === "M" ? [[6, "Grasa esencial"], [14, "Atlético"], [18, "Fitness"], [25, "Promedio"], [999, "Elevado"]]
    : [[14, "Grasa esencial"], [21, "Atlético"], [25, "Fitness"], [32, "Promedio"], [999, "Elevado"]];
  return r.find(([l]) => bf < l)[1];
}

export function compute(m, { sex, age, height }) {
  const w = num(m.weight_kg), h = num(m.height_cm) || num(height);
  const sf = {
    chest: num(m.sf_chest), midaxillary: num(m.sf_midaxillary), triceps: num(m.sf_triceps),
    subscapular: num(m.sf_subscapular), abdominal: num(m.sf_abdominal), suprailiac: num(m.sf_suprailiac), thigh: num(m.sf_thigh),
  };
  const b = bmi(w, h);
  const methods = {
    jp7: clamp(jp7(sex, age, sf)), jp3: clamp(jp3(sex, age, sf)),
    navy: clamp(navy(sex, h, num(m.neck), num(m.waist), num(m.hip), num(m.abdomen))),
    ymca: clamp(ymca(sex, w, num(m.abdomen) || num(m.waist))), cun_bae: clamp(cunBae(b, age, sex)),
    deurenberg: clamp(deurenberg(b, age, sex)),
  };
  const bio = clamp(num(m.bioimpedance_bf));
  const order = ["jp7", "jp3", "navy", "cun_bae", "deurenberg", "ymca"];
  let method = null, bf = null;
  if (bio) { method = "bioimpedance"; bf = bio; } else {
    const k = order.find((k) => methods[k] != null);
    if (k) { method = k; bf = methods[k]; }
  }
  const out = { bmi: b ? Math.round(b * 10) / 10 : null, methods, body_fat: bf, method, classification: classify(bf, sex),
    fat_mass: null, lean_mass: null, ffmi: null };
  if (bf != null && w) {
    const fat = w * bf / 100, lean = w - fat;
    out.fat_mass = Math.round(fat * 10) / 10; out.lean_mass = Math.round(lean * 10) / 10;
    if (h) { const hm = h / 100; out.ffmi = Math.round((lean / hm ** 2 + 6.1 * (1.8 - hm)) * 10) / 10; }
  }
  const waist = num(m.waist) || num(m.abdomen);
  if (waist && num(m.hip)) out.whr = Math.round(waist / num(m.hip) * 100) / 100;
  if (waist && h) out.whtr = Math.round(waist / h * 100) / 100;
  return out;
}

// Rangos válidos (los mismos que valida el servidor en apps/body/validation.py)
const CIRC = ["neck", "shoulders", "chest", "waist", "abdomen", "hip", "arm_left", "arm_right", "arm_flexed_left",
  "arm_flexed_right", "forearm_left", "forearm_right", "wrist", "thigh_left", "thigh_right", "calf_left", "calf_right"];
const SF = ["sf_chest", "sf_midaxillary", "sf_triceps", "sf_subscapular", "sf_abdominal", "sf_suprailiac", "sf_thigh"];
export const RANGES = { weight_kg: [20, 350, "kg"], height_cm: [100, 240, "cm"], bioimpedance_bf: [3, 70, "%"] };
CIRC.forEach((f) => { RANGES[f] = [10, 250, "cm"]; });
RANGES.neck = [20, 70, "cm"]; RANGES.wrist = [10, 30, "cm"];
SF.forEach((f) => { RANGES[f] = [2, 90, "mm"]; });

export function parseNum(v) {
  if (v === "" || v == null) return null;
  const n = Number(String(v).replace(",", ".").trim());
  return Number.isFinite(n) ? n : NaN;
}

/** Devuelve { clean, errors } — clean ya normalizado (altura en metros → cm). */
export function validate(values, labels = {}) {
  const errors = {}, clean = {};
  for (const [f, [lo, hi, unit]] of Object.entries(RANGES)) {
    let n = parseNum(values[f]);
    if (n === null) continue;
    if (Number.isNaN(n)) { errors[f] = "No es un número"; continue; }
    if (f === "height_cm" && n >= 1 && n <= 2.5) n = Math.round(n * 1000) / 10;
    if (n < lo || n > hi) { errors[f] = `${labels[f] || ""} debe estar entre ${lo} y ${hi} ${unit}`.trim(); continue; }
    clean[f] = n;
  }
  return { clean, errors };
}
