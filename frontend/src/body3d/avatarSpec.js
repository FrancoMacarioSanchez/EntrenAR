// Definición del avatar (sin Three.js): proporciones, ropa, pelo y morfología según las medidas.
// Unidades: metros para una persona de 1,75 m. El visor escala todo según la altura real.
// Convención: la persona mira hacia +z; su lado DERECHO está en x negativo.

export const SKIN_TONES = ["#f6d7c3", "#ebc2a2", "#d9a581", "#bd8057", "#90603e", "#5f3d27"];
export const HAIR_COLORS = [["#16110e", "Negro"], ["#3f2a1d", "Castaño oscuro"], ["#6e4a2e", "Castaño"],
  ["#b98b52", "Rubio oscuro"], ["#e2c27f", "Rubio"], ["#8f3a1c", "Colorado"], ["#9b9b9b", "Canoso"], ["#6d4ad8", "Fantasía"]];
export const CLOTH_COLORS = ["#ff5a1f", "#111827", "#f5f5f4", "#2563eb", "#16a34a", "#dc2626", "#7c3aed", "#db2777",
  "#0d9488", "#facc15", "#6b7280", "#1e3a8a"];
export const HAIR_STYLES = [["shaved", "Rapado"], ["short", "Corto"], ["curly", "Rulos"], ["long", "Largo"],
  ["ponytail", "Colita"], ["bun", "Rodete"], ["bald", "Pelado"]];
export const TOP_STYLES = [["tank", "Musculosa"], ["tee", "Remera"], ["sports", "Top deportivo"], ["none", "Sin remera"]];
export const BOTTOM_STYLES = [["shorts", "Short"], ["leggings", "Calza"], ["joggers", "Jogger"]];

export function defaultAvatar(sex = "M") {
  return {
    v: 2, sex, skin: 1, hair_style: sex === "F" ? "ponytail" : "short", hair_color: "#3f2a1d",
    top_style: sex === "F" ? "sports" : "tank", top_color: "#ff5a1f", bottom_style: sex === "F" ? "leggings" : "shorts",
    bottom_color: "#111827", shoe_color: "#f5f5f4", muscle: 0.5, fat: 0.3, use_measures: true, sculpt: {},
  };
}

/** La app personaliza solo el cuerpo: sin ropa ni pelo (el avatar es un maniquí). */
export const BODY_ONLY = true;

export const SCULPT_REGIONS = [["shoulders", "Hombros"], ["chest", "Pecho"], ["waist", "Cintura"], ["abdomen", "Abdomen"],
  ["hip", "Cadera"], ["neck", "Cuello"], ["arm", "Brazos"], ["forearm", "Antebrazos"], ["thigh", "Muslos"], ["calf", "Pantorrillas"]];

/** Moldeado manual por región (−1 a 1), solo regiones conocidas y sin ceros. */
export function cleanSculpt(sc) {
  const out = {};
  for (const [k] of SCULPT_REGIONS) {
    const v = Math.round(Math.min(1, Math.max(-1, +sc?.[k] || 0)) * 100) / 100;
    if (v) out[k] = v;
  }
  return out;
}

export function normalizeAvatar(a, sex) {
  const base = defaultAvatar(a?.sex || sex || "M");
  const out = { ...base, ...(a || {}) };
  out.muscle = Math.min(1, Math.max(0, +out.muscle || 0));
  out.fat = Math.min(1, Math.max(0, +out.fat || 0));
  out.sculpt = cleanSculpt(out.sculpt);
  return out;
}

export function randomAvatar(sex) {
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
  const hair = HAIR_STYLES.filter(([k]) => sex === "F" ? k !== "bald" && k !== "shaved" : true);
  return normalizeAvatar({
    sex, skin: Math.floor(Math.random() * SKIN_TONES.length), hair_style: pick(hair)[0], hair_color: pick(HAIR_COLORS)[0],
    top_style: pick(TOP_STYLES.filter(([k]) => sex === "F" ? k !== "none" : true))[0], top_color: pick(CLOTH_COLORS),
    bottom_style: pick(BOTTOM_STYLES)[0], bottom_color: pick(CLOTH_COLORS), shoe_color: pick(CLOTH_COLORS),
    muscle: Math.round(Math.random() * 10) / 10, fat: Math.round(Math.random() * 8) / 10, use_measures: true,
  });
}

// ----------------------------------------------------------------- utilidades
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const num = (v) => (v === "" || v == null || isNaN(+v) ? null : +v);

/** Interpola filas de objetos con Catmull-Rom (por índice) para obtener superficies suaves. */
export function smoothRows(rows, steps = 4) {
  const out = [];
  const keys = Object.keys(rows[0]).filter((k) => typeof rows[0][k] === "number");
  for (let i = 0; i < rows.length - 1; i++) {
    const p0 = rows[Math.max(0, i - 1)], p1 = rows[i], p2 = rows[i + 1], p3 = rows[Math.min(rows.length - 1, i + 2)];
    for (let s = 0; s < steps; s++) {
      const t = s / steps, t2 = t * t, t3 = t2 * t;
      const row = { ...p1 };
      for (const k of keys) {
        row[k] = 0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
          + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3);
      }
      out.push(row);
    }
  }
  out.push({ ...rows[rows.length - 1] });
  return out;
}

/** Perfil de radios suavizado para una extremidad (n muestras). */
export function smoothProfile(radii, n = 18) {
  const rows = smoothRows(radii.map((r) => ({ r })), Math.ceil(n / (radii.length - 1)));
  return rows.map((x) => Math.max(0.004, x.r));
}

// Medidas de referencia (cm) de un cuerpo "promedio": si el socio mide más/menos, el avatar se ensancha/afina.
const REF = {
  M: { neck: 38, shoulders: 116, chest: 100, waist: 84, abdomen: 88, hip: 98, arm: 33, forearm: 28, thigh: 56, calf: 37, wrist: 17 },
  F: { neck: 32, shoulders: 102, chest: 90, waist: 70, abdomen: 80, hip: 98, arm: 28, forearm: 24, thigh: 55, calf: 35, wrist: 15 },
};

export const REGIONS = ["neck", "shoulders", "chest", "waist", "abdomen", "hip", "arm", "forearm", "thigh", "calf"];
export const NEUTRAL_FACTORS = Object.fromEntries([...REGIONS, "wrist"].map((k) => [k, 1]));

/** Factor de grosor de cada región según las medidas (1 = promedio). */
export function girthFactors(a, m, refOverride) {
  const ref = { ...(REF[a.sex] || REF.M), ...(refOverride || {}) };
  const f = {};
  const get = (...keys) => {
    const vals = keys.map((k) => num(m?.[k])).filter((x) => x != null && x > 5);
    return vals.length ? vals.reduce((x, y) => x + y, 0) / vals.length : null;
  };
  const val = {
    neck: get("neck"), shoulders: get("shoulders"), chest: get("chest"), waist: get("waist"), abdomen: get("abdomen"),
    hip: get("hip"), arm: get("arm_right", "arm_left"), forearm: get("forearm_right", "forearm_left"),
    thigh: get("thigh_right", "thigh_left"), calf: get("calf_right", "calf_left"), wrist: get("wrist"),
  };
  for (const k of Object.keys(ref)) {
    f[k] = a.use_measures && val[k] ? clamp(val[k] / ref[k], 0.72, 1.55) : 1;
  }
  // si cargó la cintura pero no el abdomen (o al revés) se acompañan
  if (f.waist !== 1 && f.abdomen === 1) f.abdomen = f.waist;
  if (f.abdomen !== 1 && f.waist === 1) f.waist = 1 + (f.abdomen - 1) * 0.8;
  return f;
}

// ----------------------------------------------------------------- torso
export const TORSO = {
  M: [ // y, mitad del ancho, mitad de la profundidad, desplazamiento z, región
    [0.79, 0.105, 0.08, 0, "hip"], [0.83, 0.150, 0.105, -0.004, "hip"], [0.885, 0.168, 0.118, -0.012, "hip"],
    [0.945, 0.165, 0.117, -0.012, "hip"], [1.0, 0.153, 0.106, 0.0, "abdomen"], [1.05, 0.146, 0.101, 0.006, "abdomen"],
    [1.10, 0.143, 0.097, 0.003, "waist"], [1.17, 0.152, 0.102, 0.004, "waist"], [1.24, 0.167, 0.111, 0.009, "chest"],
    [1.31, 0.177, 0.116, 0.012, "chest"], [1.37, 0.181, 0.108, 0.004, "shoulders"], [1.415, 0.168, 0.094, -0.006, "shoulders"],
    [1.455, 0.112, 0.071, -0.012, "neck"], [1.485, 0.064, 0.058, -0.006, "neck"],
  ],
  F: [
    [0.79, 0.108, 0.085, 0, "hip"], [0.83, 0.158, 0.11, -0.008, "hip"], [0.895, 0.181, 0.126, -0.018, "hip"],
    [0.955, 0.172, 0.121, -0.016, "hip"], [1.01, 0.148, 0.101, -0.002, "abdomen"], [1.055, 0.133, 0.093, 0.004, "abdomen"],
    [1.10, 0.124, 0.088, 0.002, "waist"], [1.16, 0.132, 0.092, 0.003, "waist"], [1.23, 0.149, 0.1, 0.008, "chest"],
    [1.30, 0.157, 0.104, 0.01, "chest"], [1.355, 0.162, 0.099, 0.004, "shoulders"], [1.405, 0.153, 0.087, -0.004, "shoulders"],
    [1.445, 0.103, 0.066, -0.01, "neck"], [1.472, 0.056, 0.051, -0.005, "neck"],
  ],
};

/**
 * opts.factors: fuerza los factores de grosor (para generar morph targets sin acoplar regiones).
 * La topología (cantidad y tipo de piezas) depende SOLO de top_style, bottom_style y hair_style.
 */
export function buildSpec(avatar, measures, opts = {}) {
  const a = normalizeAvatar(avatar);
  const F = a.sex === "F";
  const g = opts.factors ? { ...NEUTRAL_FACTORS, ...opts.factors } : girthFactors(a, measures);
  const mus = 1 + (a.muscle - 0.5) * 0.28;      // volumen muscular
  const fat = a.fat - 0.3;                       // grasa respecto de un cuerpo promedio
  const parts = [];
  const add = (p) => { parts.push(p); return p; };

  // ---- torso (filas suavizadas)
  const rows = TORSO[a.sex === "F" ? "F" : "M"].map(([y, w, d, dz, region]) => {
    let fw = 1, fd = 1, zz = dz;
    if (region === "hip") { fw = g.hip * (1 + fat * 0.18); fd = g.hip * (1 + fat * 0.2); }
    if (region === "abdomen") { fw = g.abdomen * (1 + fat * 0.3); fd = g.abdomen * (1 + fat * 0.5); zz += Math.max(0, fat) * 0.035 * g.abdomen; }
    if (region === "waist") { fw = g.waist * (1 + fat * 0.28); fd = g.waist * (1 + fat * 0.35); }
    if (region === "chest") { fw = g.chest * (1 + (mus - 1) * 0.6 + fat * 0.1); fd = g.chest * (1 + (mus - 1) * 0.5 + fat * 0.12); }
    if (region === "shoulders") { fw = g.shoulders * (1 + (mus - 1) * 0.7); fd = 1 + (mus - 1) * 0.3; }
    if (region === "neck") { fw = g.neck * (1 + (mus - 1) * 0.6); fd = g.neck; }
    return { y, w: w * fw, d: d * fd, dz: zz };
  });
  const torso = smoothRows(rows, 5);
  add({ type: "loft", rows: torso, mat: "skin", zone: "torso" });

  // pectorales / busto y glúteos
  if (F) {
    const bust = g.chest * (1 + fat * 0.25);
    for (const s of [-1, 1]) add({ type: "ellipsoid", pos: [s * 0.066, 1.272, 0.072 * g.chest], r: [0.066 * bust, 0.062 * bust, 0.058 * bust], mat: "chest", zone: "chest" });
  } else {
    for (const s of [-1, 1]) add({ type: "ellipsoid", pos: [s * 0.072, 1.305, 0.072 * g.chest], r: [0.082 * mus, 0.06 * mus, 0.05 * mus], mat: "chest", zone: "chest" });
  }
  for (const s of [-1, 1]) {
    const gl = g.hip * (1 + fat * 0.15) * (F ? 1.08 : 1);
    add({ type: "ellipsoid", pos: [s * 0.072, 0.9, -0.064 * gl], r: [0.088 * gl, 0.1 * gl, 0.072 * gl], mat: "bottom", zone: "hip" });
  }

  // ---- cuello y cabeza
  const neckR = (F ? 0.05 : 0.058) * g.neck * (1 + (mus - 1) * 0.5);
  add({ type: "lathe", from: [0, 1.455, -0.008], to: [0, 1.6, 0.0], profile: smoothProfile([neckR * 1.15, neckR, neckR * 0.96, neckR * 0.92]), mat: "skin", zone: "neck" });
  const head = { c: [0, 1.668, 0.006], r: F ? [0.082, 0.106, 0.096] : [0.088, 0.112, 0.1] };
  add({ type: "ellipsoid", pos: head.c, r: head.r, mat: "skin", zone: "neck" });
  add({ type: "ellipsoid", pos: [0, 1.6, 0.04], r: [head.r[0] * 0.78, 0.05, head.r[2] * 0.7], mat: "skin" }); // mandíbula
  for (const s of [-1, 1]) {
    add({ type: "ellipsoid", pos: [s * head.r[0] * 0.98, 1.665, 0.0], r: [0.013, 0.026, 0.018], mat: "skin", attach: true });            // orejas
    add({ type: "ellipsoid", pos: [s * 0.032, 1.676, head.r[2] * 0.86], r: [0.013, 0.01, 0.008], mat: "eye" });              // ojos
    add({ type: "ellipsoid", pos: [s * 0.033, 1.697, head.r[2] * 0.85], r: [0.02, 0.0045, 0.006], mat: "brow", rot: [0, 0, s * -0.12] }); // cejas
  }
  add({ type: "ellipsoid", pos: [0, 1.655, head.r[2] * 0.97], r: [0.011, 0.02, 0.014], mat: "skin", attach: true }); // nariz
  add({ type: "ellipsoid", pos: [0, 1.622, head.r[2] * 0.86], r: [0.019, 0.005, 0.006], mat: "lips" });  // boca

  // ---- pelo
  const hr = head.r;
  // dos casquetes: uno derecho (coronilla y frente) y otro inclinado hacia atrás (nuca)
  const cap = (scale, theta, tilt = -0.42) => {
    add({ type: "cap", pos: head.c, r: [hr[0] * scale * 0.995, hr[1] * scale * 0.995, hr[2] * scale * 0.995], theta: 1.12, rot: [0.18, 0, 0], mat: "hair" });
    add({ type: "cap", pos: head.c, r: [hr[0] * scale, hr[1] * scale, hr[2] * scale], theta, rot: [tilt, 0, 0], mat: "hair" });
  };
  switch (a.hair_style) {
    case "shaved": cap(1.014, 1.62, -0.62); break;
    case "short": cap(1.055, 1.66, -0.62); break;
    case "curly":
      cap(1.12, 1.7, -0.6);
      for (let i = 0; i < 9; i++) {
        const ang = (i / 9) * Math.PI * 2;
        add({ type: "ellipsoid", pos: [head.c[0] + Math.cos(ang) * hr[0] * 0.95, head.c[1] + 0.06 + Math.sin(i) * 0.012, head.c[2] - 0.02 + Math.sin(ang) * hr[2] * 0.9], r: [0.035, 0.032, 0.035], mat: "hair" });
      }
      break;
    case "long":
      cap(1.06, 1.72, -0.55);
      add({ type: "ellipsoid", pos: [0, 1.53, -0.055], r: [hr[0] * 1.05, 0.15, 0.05], mat: "hair" });
      for (const s of [-1, 1]) add({ type: "ellipsoid", pos: [s * hr[0] * 0.92, 1.58, 0.0], r: [0.022, 0.1, 0.045], mat: "hair" });
      break;
    case "ponytail":
      cap(1.055, 1.66, -0.6);
      add({ type: "ellipsoid", pos: [0, 1.715, -0.095], r: [0.028, 0.028, 0.028], mat: "hair" });
      add({ type: "lathe", from: [0, 1.715, -0.11], to: [0, 1.5, -0.13], profile: smoothProfile([0.03, 0.036, 0.03, 0.016]), mat: "hair" });
      break;
    case "bun":
      cap(1.055, 1.66, -0.6);
      add({ type: "ellipsoid", pos: [0, 1.755, -0.06], r: [0.046, 0.042, 0.046], mat: "hair" });
      break;
    default: break; // pelado
  }

  // ---- brazos
  const zones = {};
  const sw = (F ? 0.183 : 0.2) * (1 + (g.shoulders - 1) * 0.8) * (1 + (mus - 1) * 0.35);
  const armF = g.arm * (1 + (mus - 1) * 0.9 + fat * 0.22) * (F ? 0.86 : 1);
  const foreF = g.forearm * (1 + (mus - 1) * 0.6 + fat * 0.1) * (F ? 0.86 : 1);
  for (const s of [-1, 1]) {
    const side = s < 0 ? "right" : "left";
    const J = [s * sw, 1.405, -0.004];
    const E = [s * (sw + 0.055), 1.13, -0.018];
    const W = [s * (sw + 0.085), 0.875, 0.012];
    const H = [s * (sw + 0.095), 0.775, 0.026];
    const delt = (F ? 0.052 : 0.062) * mus * g.shoulders;
    add({ type: "ellipsoid", pos: [s * (sw + 0.006), 1.395, 0], r: [delt, delt * 1.18, delt * 1.08], mat: "shoulder", zone: "shoulders" });
    const ua = smoothProfile([0.054, 0.058, 0.06, 0.054, 0.046, 0.04].map((r) => r * armF));
    add({ type: "lathe", from: J, to: E, profile: ua, mat: "skin", zone: `arm_${side}` });
    add({ type: "ellipsoid", pos: E, r: [0.04 * foreF, 0.042 * foreF, 0.04 * foreF], mat: "skin", zone: `forearm_${side}` });
    const fa = smoothProfile([0.041, 0.047, 0.045, 0.038, 0.031, 0.027].map((r) => r * foreF));
    add({ type: "lathe", from: E, to: W, profile: fa, mat: "skin", zone: `forearm_${side}` });
    add({ type: "lathe", from: W, to: H, profile: smoothProfile([0.026, 0.034, 0.035, 0.026, 0.012].map((r) => r * (F ? 0.9 : 1))), mat: "skin", zone: "wrist", flatten: 0.55 });
    zones[`arm_${side}`] = ring(J, E, 0.42, ua, 1.22);
    zones[`forearm_${side}`] = ring(E, W, 0.22, fa, 1.25);
    if (s < 0) zones.wrist = ring(E, W, 0.97, fa, 1.45);
    if (a.top_style === "tee") add({ type: "lathe", from: J, to: lerp3(J, E, 0.42), profile: ua.slice(0, 9).map((r) => r * 1.16 + 0.004), mat: "top", zone: `arm_${side}`, open: true });
  }

  // ---- piernas
  const thF = g.thigh * (1 + (mus - 1) * 0.7 + fat * 0.25) * (F ? 1.04 : 1);
  const caF = g.calf * (1 + (mus - 1) * 0.6 + fat * 0.12);
  for (const s of [-1, 1]) {
    const side = s < 0 ? "right" : "left";
    const Hj = [s * (F ? 0.094 : 0.09), 0.885, -0.004];
    const K = [s * 0.098, 0.49, 0.008];
    const A = [s * 0.095, 0.085, -0.012];
    const th = smoothProfile([0.094, 0.092, 0.084, 0.072, 0.06, 0.052].map((r) => r * thF));
    add({ type: "lathe", from: Hj, to: K, profile: th, mat: "skin", zone: `thigh_${side}` });
    add({ type: "ellipsoid", pos: K, r: [0.052 * caF, 0.058, 0.055 * caF], mat: "skin", zone: `calf_${side}` });
    const ca = smoothProfile([0.05, 0.058, 0.062, 0.052, 0.04, 0.032, 0.029].map((r) => r * caF));
    add({ type: "lathe", from: K, to: A, profile: ca, mat: "skin", zone: `calf_${side}` });
    add({ type: "ellipsoid", pos: [s * 0.095, 0.048, 0.03], r: [0.047, 0.045, 0.112], mat: "shoe" });
    add({ type: "ellipsoid", pos: [s * 0.095, 0.015, 0.03], r: [0.05, 0.016, 0.118], mat: "sole" });
    zones[`thigh_${side}`] = ring(Hj, K, 0.32, th, 1.18);
    zones[`calf_${side}`] = ring(K, A, 0.3, ca, 1.2);
    // pantalón
    const cover = a.bottom_style === "shorts" ? 0.45 : a.bottom_style === "leggings" ? 1 : 1;
    const loose = a.bottom_style === "joggers" ? 1.16 : a.bottom_style === "shorts" ? 1.1 : 1.025;
    const thCov = th.slice(0, Math.max(3, Math.round(th.length * cover)));
    add({ type: "lathe", from: Hj, to: lerp3(Hj, K, cover), profile: thCov.map((r) => r * loose + 0.003), mat: "bottom", zone: `thigh_${side}`, open: true });
    if (a.bottom_style !== "shorts") {
      const cut = a.bottom_style === "joggers" ? 0.93 : 0.86;
      const caCov = ca.slice(0, Math.round(ca.length * cut));
      add({ type: "lathe", from: K, to: lerp3(K, A, cut), profile: caCov.map((r) => r * loose + 0.003), mat: "bottom", zone: `calf_${side}`, open: true });
      add({ type: "ellipsoid", pos: K, r: [0.052 * caF * loose + 0.003, 0.06, 0.055 * caF * loose + 0.003], mat: "bottom", zone: `calf_${side}` });
      if (a.bottom_style === "joggers") add({ type: "lathe", from: lerp3(K, A, 0.88), to: lerp3(K, A, 0.96), profile: [0.04, 0.038, 0.037], mat: "bottom", open: true });
    }
  }

  // ---- ropa del torso (capas un poco más grandes que el cuerpo)
  // por índice de fila de control (no por altura) para que la topología no cambie entre hombre/mujer
  const band = (c0, c1, grow, mat) => {
    const rr = torso.slice(c0 * 5, c1 * 5 + 1).map((r) => ({ ...r, w: r.w * grow + 0.002, d: r.d * grow + 0.002 }));
    add({ type: "loft", rows: rr, mat, zone: "torso", open: true });
  };
  band(0, 4, 1.035, "bottom");
  if (a.top_style === "tank") band(3, 11, 1.03, "top");
  if (a.top_style === "tee") band(3, 11, 1.045, "top");
  if (a.top_style === "sports") band(8, 10, 1.03, "top");

  // ---- anillos de medición del torso
  const at = (y) => torso.reduce((best, r) => (Math.abs(r.y - y) < Math.abs(best.y - y) ? r : best), torso[0]);
  const tz = (id, y, k = 1.07, extra = 0) => {
    const r = at(y);
    zones[id] = { pos: [0, y, r.dz + extra], r: r.w * k, flat: (r.d * k + extra) / (r.w * k), tilt: 0 };
  };
  zones.neck = { pos: [0, 1.535, -0.004], r: neckR * 1.3, flat: 0.95, tilt: 0 };
  zones.shoulders = { pos: [0, 1.395, 0], r: sw + (F ? 0.052 : 0.062) * mus * 1.05, flat: 0.48, tilt: 0 };
  tz("chest", F ? 1.272 : 1.3, 1.1, F ? 0.03 : 0.012);
  tz("waist", 1.1);
  tz("abdomen", 1.03, 1.08);
  tz("hip", F ? 0.915 : 0.905, 1.12, 0.012);

  return {
    parts, zones, avatar: a, scale: (num(measures?.height_cm) || num(a.height_cm) || 175) / 175,
    colors: {
      skin: SKIN_TONES[clamp(a.skin | 0, 0, SKIN_TONES.length - 1)], hair: a.hair_color, top: a.top_color,
      bottom: a.bottom_color, shoe: a.shoe_color, sole: "#e7e5e4", eye: "#1c1917", brow: a.hair_color === "#9b9b9b" ? "#6b6b6b" : a.hair_color,
      lips: "#b4685a",
      chest: a.top_style === "none" ? "skin" : "top",
      shoulder: a.top_style === "tee" ? "top" : "skin",
    },
  };
}

function lerp3(p, q, t) { return [lerp(p[0], q[0], t), lerp(p[1], q[1], t), lerp(p[2], q[2], t)]; }

function ring(from, to, t, profile, k) {
  const pos = lerp3(from, to, t);
  const r = profile[Math.min(profile.length - 1, Math.round(t * (profile.length - 1)))] * k;
  const dx = to[0] - from[0], dy = to[1] - from[1];
  return { pos, r, flat: 1, tilt: Math.atan2(dx, -dy) };
}

/** Qué zona corresponde a una altura del torso (cuando se toca el tronco). */
export function torsoZoneAt(y) {
  if (y > 1.44) return "neck";
  if (y > 1.36) return "shoulders";
  if (y > 1.2) return "chest";
  if (y > 1.07) return "waist";
  if (y > 0.98) return "abdomen";
  return "hip";
}
