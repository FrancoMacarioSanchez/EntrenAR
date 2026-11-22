// Morph targets del avatar sobre UNA malla base continua.
//  - Cuerpo: superficie suave (sdfBody.js). Su topología es siempre la misma, para cualquier ropa o persona.
//  - Accesorios de la cabeza (pelo, ojos, cejas, nariz, orejas, boca): dependen solo del peinado.
//  - La ropa se PINTA sobre el cuerpo (color por vértice): cambiar de prenda no regenera nada.
import { BODY_ONLY, buildSpec, girthFactors, normalizeAvatar, REGIONS } from "../avatarSpec.js";
import { computeNormals, SLOTS, specToBuffers, ZONE_IDS } from "./meshgen.js";
import { bodyModel, COMP, meshBody, projectTo, zoneOfVertex } from "./sdfBody.js";

export const MESH_VERSION = 3; // subir si cambia la malla (invalida la caché del navegador)
export const STYLE_KEYS = ["hair_style"];
export const styleKey = (a) => `v${MESH_VERSION}|${a.hair_style}`;

export const BASE = { sex: "M", muscle: 0.5, fat: 0.3, use_measures: true };
export const REGION_STEP = 0.4; // el target de cada región representa +40% de perímetro
export const SCULPT_LIMIT = 1;  // el moldeado manual suma hasta ±1 al peso de cada región

/** Definición de cada shape key. Los nombres son los que debe usar un modelo GLB externo. */
// `k`: el target se muestrea a mitad de camino y se multiplica (aproximación lineal más fiel, sin pliegues).
export const MORPH_TARGETS = [
  { name: "sex_female", avatar: { sex: "F" }, k: 1 },
  { name: "muscle", avatar: { muscle: 0.75 }, k: 2 },
  { name: "fat", avatar: { fat: 0.65 }, k: 2 },
  ...REGIONS.map((r) => ({ name: `girth_${r}`, factors: { [r]: 1 + REGION_STEP / 2 }, k: 2 })),
];

/** Región moldeable que corresponde a una zona tocada. */
export const regionOfZone = (zone) => {
  if (!zone) return null;
  if (zone === "wrist") return "forearm";
  return zone.replace(/_(right|left)$/, "");
};

/** Pesos (pueden ser negativos: el shader interpola/extrapola linealmente). */
export function computeWeights(avatar, measures, ref) {
  const a = normalizeAvatar(avatar);
  const f = girthFactors(a, measures, ref);
  const sculpt = a.sculpt || {};
  const w = {
    sex_female: a.sex === "F" ? 1 : 0,
    muscle: (a.muscle - BASE.muscle) / (1 - BASE.muscle),
    fat: (a.fat - BASE.fat) / (1 - BASE.fat),
  };
  for (const r of REGIONS) {
    const s = Math.max(-SCULPT_LIMIT, Math.min(SCULPT_LIMIT, +sculpt[r] || 0));
    w[`girth_${r}`] = (f[r] - 1) / REGION_STEP + s;
  }
  return w;
}

// ------------------------------------------------------------------ cuerpo (una vez por dispositivo)
let bodyCache = null;
export const getBodyCache = () => bodyCache;
export const setBodyCache = (b) => { bodyCache = b; };

/** Malla del cuerpo + deltas de los 13 targets. Serializable (se guarda en IndexedDB). */
export function buildBody() {
  const mBase = bodyModel(BASE, {});
  const base = meshBody(mBase);
  const adj = adjacency(base.indices, base.vertexCount);
  const targets = MORPH_TARGETS.map((t) => {
    const m = bodyModel({ ...BASE, ...(t.avatar || {}) }, t.factors || {});
    const p = projectTo(base, mBase, m);
    const k = t.k || 1;
    const delta = new Float32Array(p.positions.length);
    for (let i = 0; i < delta.length; i++) delta[i] = (p.positions[i] - base.positions[i]) * k;
    smoothField(delta, adj, 10);
    return { name: t.name, delta, head: m.head, k };
  });
  const zones = new Uint8Array(base.vertexCount);
  for (let v = 0; v < base.vertexCount; v++) {
    zones[v] = Math.max(0, ZONE_IDS.indexOf(zoneOfVertex(base.comp[v], base.positions[v * 3 + 1])));
  }
  return {
    version: MESH_VERSION, positions: base.positions, indices: base.indices, comp: base.comp, zones,
    vertexCount: base.vertexCount, head: mBase.head, targets,
  };
}

function bodyData() {
  if (!bodyCache || bodyCache.version !== MESH_VERSION) bodyCache = buildBody();
  return bodyCache;
}

/** Vecinos de cada vértice (CSR). */
function adjacency(indices, V) {
  const sets = Array.from({ length: V }, () => new Set());
  for (let i = 0; i < indices.length; i += 3) {
    const a = indices[i], b = indices[i + 1], c = indices[i + 2];
    sets[a].add(b); sets[a].add(c); sets[b].add(a); sets[b].add(c); sets[c].add(a); sets[c].add(b);
  }
  const start = new Uint32Array(V + 1);
  for (let v = 0; v < V; v++) start[v + 1] = start[v] + sets[v].size;
  const list = new Uint32Array(start[V]);
  for (let v = 0; v < V; v++) { let j = start[v]; for (const n of sets[v]) list[j++] = n; }
  return { start, list };
}

/** Suaviza un campo vectorial sobre la malla (los deltas de vértices vecinos quedan parecidos: sin pliegues). */
function smoothField(f, { start, list }, iterations) {
  const tmp = new Float32Array(f.length);
  for (let it = 0; it < iterations; it++) {
    for (let v = 0; v < start.length - 1; v++) {
      const n = start[v + 1] - start[v];
      let x = 0, y = 0, z = 0;
      for (let j = start[v]; j < start[v + 1]; j++) { const u = list[j] * 3; x += f[u]; y += f[u + 1]; z += f[u + 2]; }
      const o = v * 3;
      if (!n) { tmp[o] = f[o]; tmp[o + 1] = f[o + 1]; tmp[o + 2] = f[o + 2]; continue; }
      tmp[o] = f[o] * 0.5 + (x / n) * 0.5; tmp[o + 1] = f[o + 1] * 0.5 + (y / n) * 0.5; tmp[o + 2] = f[o + 2] * 0.5 + (z / n) * 0.5;
    }
    f.set(tmp);
  }
}

// ------------------------------------------------------------------ accesorios de la cabeza
function attachments(avatar) {
  const spec = buildSpec({ ...BASE, hair_style: avatar.hair_style }, {}, { factors: {} });
  const parts = spec.parts.filter((p) => p.attach || ["hair", "eye", "brow", "lips"].includes(p.mat));
  return specToBuffers({ parts });
}

/** Lleva los accesorios de la cabeza base a la cabeza de otro cuerpo (misma topología). */
function mapHead(pos, from, to) {
  const out = new Float32Array(pos.length);
  for (let i = 0; i < pos.length; i += 3) {
    for (let k = 0; k < 3; k++) out[i + k] = to.c[k] + (pos[i + k] - from.c[k]) * (to.r[k] / from.r[k]);
  }
  return out;
}

/** Malla completa (cuerpo + accesorios) y deltas de los 13 targets para un peinado. */
export function generateMorphData(style) {
  const B = bodyData();
  const acc = attachments(style);
  const nb = B.vertexCount, na = acc.vertexCount, V = nb + na;
  const positions = new Float32Array(V * 3);
  positions.set(B.positions); positions.set(acc.positions, nb * 3);
  const indices = new Uint32Array(B.indices.length + acc.indices.length);
  indices.set(B.indices);
  for (let i = 0; i < acc.indices.length; i++) indices[B.indices.length + i] = acc.indices[i] + nb;
  const comp = new Uint8Array(V); comp.set(B.comp);
  const fixedSlots = new Uint8Array(V).fill(255); fixedSlots.set(acc.slots, nb);
  const zones = new Uint8Array(V); zones.set(B.zones);
  const targets = B.targets.map((t) => {
    const delta = new Float32Array(V * 3);
    delta.set(t.delta);
    const ap = mapHead(acc.positions, B.head, t.head);
    for (let i = 0; i < ap.length; i++) delta[nb * 3 + i] = (ap[i] - acc.positions[i]) * t.k;
    return { name: t.name, delta };
  });
  const normals = computeNormals(positions, indices);
  return { style: styleKey(style), positions, normals, indices, comp, fixedSlots, zones, vertexCount: V, bodyVertexCount: nb, targets };
}

/** Aplica pesos en la CPU (para recalcular normales y para tests). */
export function morphPositions(data, weights, out) {
  const P = out || new Float32Array(data.positions.length);
  P.set(data.positions);
  for (const t of data.targets) {
    const w = weights[t.name] || 0;
    if (Math.abs(w) < 1e-4) continue;
    const d = t.delta;
    for (let i = 0; i < P.length; i++) P[i] += d[i] * w;
  }
  return P;
}

// ------------------------------------------------------------------ ropa pintada
let paintModel = null;
const S = Object.fromEntries(SLOTS.map((s, i) => [s, i]));

/** Slot de color de cada vértice según la ropa elegida (se recalcula al cambiar de prenda, sin regenerar la malla). */
export function paintSlots(data, avatar, out) {
  const a = normalizeAvatar(avatar);
  const F = a.sex === "F";
  paintModel ||= bodyModel(BASE, {});
  const m = paintModel;
  const slots = out || new Uint8Array(data.vertexCount);
  const P = data.positions;
  const waistband = a.bottom_style === "leggings" && F ? 1.02 : 0.985;
  const topStyle = F && a.top_style === "none" ? "sports" : a.top_style;
  const tParam = (c, x, y, z) => { // posición a lo largo del brazo (0 hombro → 1 codo)
    const A = m.arms[c & 1];
    const v = [A.E[0] - A.J[0], A.E[1] - A.J[1], A.E[2] - A.J[2]];
    return ((x - A.J[0]) * v[0] + (y - A.J[1]) * v[1] + (z - A.J[2]) * v[2]) / (v[0] ** 2 + v[1] ** 2 + v[2] ** 2);
  };
  for (let v = 0; v < data.vertexCount; v++) {
    if (data.fixedSlots[v] !== 255) { slots[v] = data.fixedSlots[v]; continue; }
    if (BODY_ONLY) { slots[v] = S.skin; continue; }
    const x = P[v * 3], y = P[v * 3 + 1], z = P[v * 3 + 2];
    const c = data.comp[v], base = c >= COMP.deltoid ? c - (c & 1) : c, ax = Math.abs(x);
    let s = S.skin;
    // calzado
    if (base === COMP.foot) s = y < 0.024 ? S.sole : S.shoe;
    // pantalón
    if (base === COMP.torso && y < waistband) s = S.bottom;
    if (base === COMP.thigh) {
      if (a.bottom_style !== "shorts" || y > 0.7 - (ax > 0.13 ? 0.01 : 0)) s = S.bottom;
    }
    if (base === COMP.calf && a.bottom_style !== "shorts" && y > (a.bottom_style === "joggers" ? 0.115 : 0.15)) s = S.bottom;
    // parte de arriba
    if (base === COMP.torso) {
      const front = z > 0.02;
      if (topStyle === "tank") {
        const neckline = 1.425 - (front ? 0.05 * Math.max(0, 1 - (ax / 0.085) ** 2) : 0.01);
        const armhole = ax > 0.128 && y > 1.27;
        if (y >= waistband && y < neckline && !armhole) s = S.top;
      } else if (topStyle === "tee") {
        const neckline = 1.45 - (front ? 0.025 * Math.max(0, 1 - (ax / 0.07) ** 2) : 0);
        if (y >= 0.95 && y < neckline) s = S.top;
      } else if (topStyle === "sports") {
        const lo = F ? 1.19 : 1.21;
        const strap = y >= 1.38 && y < 1.47 && ax > 0.045 && ax < 0.085;
        if ((y >= lo && y < 1.385) || strap) s = S.top;
      }
    }
    if (topStyle === "tee" && (base === COMP.deltoid || (base === COMP.upperarm && tParam(c, x, y, z) < 0.42))) s = S.top;
    slots[v] = s;
  }
  return slots;
}
