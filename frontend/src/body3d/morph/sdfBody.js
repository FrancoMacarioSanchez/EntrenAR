// Cuerpo como UNA sola superficie continua (campo de distancia con uniones suaves).
// No hay piezas pegadas: tronco, cuello, cabeza, brazos y piernas se funden con "smooth min".
// Sin Three.js: lo usan el Web Worker, el hilo principal (anillos y pintura de ropa) y los tests en Node.
import { normalizeAvatar, NEUTRAL_FACTORS, smoothProfile, smoothRows, torsoZoneAt, TORSO } from "../avatarSpec.js";

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

// ------------------------------------------------------------------ componentes
// Pares: índice par = lado DERECHO de la persona (x negativo), impar = izquierdo.
export const COMP = {
  none: 0, torso: 1, neck: 2, head: 3, deltoid: 4, upperarm: 6, forearm: 8, hand: 10, thigh: 12, calf: 14, foot: 16,
};
const side = (base, s) => base + (s < 0 ? 0 : 1);

// ------------------------------------------------------------------ modelo paramétrico
/** Parámetros geométricos del cuerpo (mismas proporciones que avatarSpec.js). */
export function bodyModel(avatar, factors) {
  const a = normalizeAvatar(avatar);
  const F = a.sex === "F";
  const g = { ...NEUTRAL_FACTORS, ...(factors || {}) };
  const mus = 1 + (a.muscle - 0.5) * 0.28;
  const fat = a.fat - 0.3;

  // tronco: filas de elipses suavizadas → tabla cada 2 mm
  // multiplicadores por fila, suavizados entre regiones vecinas (evita "rollos" al extrapolar)
  const src = TORSO[F ? "F" : "M"];
  const mul = src.map(([, , , , region]) => {
    let fw = 1, fd = 1, zz = 0;
    if (region === "hip") { fw = g.hip * (1 + fat * 0.18); fd = g.hip * (1 + fat * 0.2); }
    if (region === "abdomen") { fw = g.abdomen * (1 + fat * 0.3); fd = g.abdomen * (1 + fat * 0.5); zz = Math.max(0, fat) * 0.035 * g.abdomen; }
    if (region === "waist") { fw = g.waist * (1 + fat * 0.28); fd = g.waist * (1 + fat * 0.35); }
    if (region === "chest") { fw = g.chest * (1 + (mus - 1) * 0.6 + fat * 0.1); fd = g.chest * (1 + (mus - 1) * 0.5 + fat * 0.12); }
    if (region === "shoulders") { fw = g.shoulders * (1 + (mus - 1) * 0.7); fd = 1 + (mus - 1) * 0.3; }
    if (region === "neck") { fw = g.neck * (1 + (mus - 1) * 0.6); fd = g.neck; }
    return [fw, fd, zz];
  });
  for (let pass = 0; pass < 2; pass++) {
    const prev = mul.map((r) => [...r]);
    for (let i = 1; i < mul.length - 1; i++) {
      // el cuello se deja fuera del promedio para no ensanchar los hombros
      if (src[i][4] === "neck" || src[i - 1][4] === "neck" || src[i + 1][4] === "neck") continue;
      for (let k = 0; k < 3; k++) mul[i][k] = prev[i - 1][k] * 0.25 + prev[i][k] * 0.5 + prev[i + 1][k] * 0.25;
    }
  }
  const rows = src.map(([y, w, d, dz], i) => ({ y, w: w * mul[i][0], d: d * mul[i][1], dz: dz + mul[i][2] }));
  const sm = smoothRows(rows, 5);
  const y0 = sm[0].y, y1 = sm[sm.length - 1].y, STEP = 0.002;
  const n = Math.ceil((y1 - y0) / STEP) + 1;
  const tw = new Float32Array(n), td = new Float32Array(n), tz = new Float32Array(n);
  for (let i = 0, j = 0; i < n; i++) {
    const y = y0 + i * STEP;
    while (j < sm.length - 2 && sm[j + 1].y < y) j++;
    const A = sm[j], B = sm[j + 1], t = clamp((y - A.y) / (B.y - A.y || 1), 0, 1);
    tw[i] = A.w + (B.w - A.w) * t; td[i] = A.d + (B.d - A.d) * t; tz[i] = A.dz + (B.dz - A.dz) * t;
  }
  const torso = { y0, y1, STEP, n, tw, td, tz };

  const ells = []; // elipsoides del tronco (busto/pectorales y glúteos)
  if (F) {
    const bust = g.chest * (1 + fat * 0.25);
    for (const s of [-1, 1]) ells.push({ c: [s * 0.066, 1.272, 0.072 * g.chest], r: [0.066 * bust, 0.062 * bust, 0.058 * bust] });
  } else {
    for (const s of [-1, 1]) ells.push({ c: [s * 0.072, 1.305, 0.068 * g.chest], r: [0.08 * mus, 0.058 * mus, 0.048 * mus] });
  }
  for (const s of [-1, 1]) {
    const gl = g.hip * (1 + fat * 0.15) * (F ? 1.08 : 1);
    ells.push({ c: [s * 0.072, 0.9, -0.064 * gl], r: [0.088 * gl, 0.1 * gl, 0.072 * gl] });
  }

  const neckR = (F ? 0.05 : 0.058) * g.neck * (1 + (mus - 1) * 0.5);
  const neck = limb([0, 1.44, -0.01], [0, 1.6, 0.0], [neckR * 1.18, neckR, neckR * 0.96, neckR * 0.92]);
  const headR = F ? [0.082, 0.106, 0.096] : [0.088, 0.112, 0.1];
  const head = { c: [0, 1.668, 0.006], r: headR.map((v) => v * (1 + Math.max(0, fat) * 0.04)) };
  const jaw = { c: [0, 1.6, 0.04], r: [head.r[0] * 0.78, 0.05, head.r[2] * 0.7] };

  // brazos (algo más abiertos que antes para que no se fundan con el tronco)
  const sw = (F ? 0.183 : 0.2) * (1 + (g.shoulders - 1) * 0.8) * (1 + (mus - 1) * 0.35);
  const armF = g.arm * (1 + (mus - 1) * 0.9 + fat * 0.22) * (F ? 0.86 : 1);
  const foreF = g.forearm * (1 + (mus - 1) * 0.6 + fat * 0.1) * (F ? 0.86 : 1);
  const thF = g.thigh * (1 + (mus - 1) * 0.7 + fat * 0.25) * (F ? 1.04 : 1);
  const caF = g.calf * (1 + (mus - 1) * 0.6 + fat * 0.12);
  const arms = [], legs = [];
  for (const s of [-1, 1]) {
    const J = [s * sw, 1.405, -0.004];
    const E = [s * (sw + 0.085), 1.135, -0.02];
    const W = [s * (sw + 0.13), 0.88, 0.01];
    const H = [s * (sw + 0.145), 0.775, 0.022];
    const delt = (F ? 0.052 : 0.062) * mus * g.shoulders;
    arms.push({
      s, J, E, W, H,
      delt: { c: [s * (sw + 0.004), 1.392, 0], r: [delt, delt * 1.18, delt * 1.08] },
      upper: limb(J, E, [0.054, 0.058, 0.06, 0.054, 0.046, 0.04].map((r) => r * armF)),
      elbow: { c: E, r: [0.04 * foreF, 0.042 * foreF, 0.04 * foreF] },
      fore: limb(E, W, [0.041, 0.047, 0.045, 0.038, 0.031, 0.027].map((r) => r * foreF)),
      hand: limb(W, H, [0.026, 0.034, 0.035, 0.028, 0.016].map((r) => r * (F ? 0.9 : 1)), 0.55),
    });
    const Hj = [s * (F ? 0.094 : 0.09), 0.885, -0.004];
    const K = [s * 0.1, 0.49, 0.008];
    const A = [s * 0.098, 0.085, -0.012];
    legs.push({
      s, Hj, K, A,
      thigh: limb(Hj, K, [0.094, 0.092, 0.084, 0.072, 0.06, 0.052].map((r) => r * thF)),
      knee: { c: K, r: [0.052 * caF, 0.058, 0.055 * caF] },
      calf: limb(K, A, [0.05, 0.058, 0.062, 0.052, 0.04, 0.032, 0.029].map((r) => r * caF)),
      shoe: { c: [s * 0.098, 0.05, 0.03], r: [0.047, 0.047, 0.112] },
      sole: { c: [s * 0.098, 0.018, 0.03], r: [0.05, 0.02, 0.118] },
    });
  }
  const m = { F, torso, ells, neck, head, jaw, arms, legs };
  m.bounds = groupBounds(m);
  return m;
}

function limb(a, b, radii, flat = 1) {
  const prof = smoothProfile(radii, 24);
  const v = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  return { a, b, v, len2: v[0] * v[0] + v[1] * v[1] + v[2] * v[2], prof, flat, rmax: Math.max(...prof) };
}

function groupBounds(m) {
  const box = () => [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  const addPt = (b, p, r) => { for (let i = 0; i < 3; i++) { b[i] = Math.min(b[i], p[i] - r); b[i + 3] = Math.max(b[i + 3], p[i] + r); } };
  const arm = m.arms.map((A) => {
    const b = box();
    for (const p of [A.J, A.E, A.W, A.H]) addPt(b, p, 0.1);
    addPt(b, A.delt.c, 0.1);
    return b;
  });
  const leg = m.legs.map((L) => {
    const b = box();
    for (const p of [L.Hj, L.K, L.A]) addPt(b, p, 0.16);
    addPt(b, L.shoe.c, 0.14);
    return b;
  });
  return { arm, leg };
}

// ------------------------------------------------------------------ primitivas
function sEll(x, y, z, e) {
  const px = (x - e.c[0]) / e.r[0], py = (y - e.c[1]) / e.r[1], pz = (z - e.c[2]) / e.r[2];
  const k0 = Math.sqrt(px * px + py * py + pz * pz);
  const k1 = Math.sqrt((px / e.r[0]) ** 2 + (py / e.r[1]) ** 2 + (pz / e.r[2]) ** 2);
  return k1 < 1e-9 ? -Math.min(...e.r) : (k0 * (k0 - 1)) / k1;
}

function sLimb(x, y, z, L) {
  const dx = x - L.a[0], dy = y - L.a[1], dz = z - L.a[2];
  let t = (dx * L.v[0] + dy * L.v[1] + dz * L.v[2]) / L.len2;
  t = t < 0 ? 0 : t > 1 ? 1 : t;
  const px = dx - L.v[0] * t, py = dy - L.v[1] * t;
  let pz = dz - L.v[2] * t;
  if (L.flat !== 1) pz /= L.flat;
  const f = t * (L.prof.length - 1), i = Math.min(L.prof.length - 2, f | 0), u = f - i;
  const r = L.prof[i] + (L.prof[i + 1] - L.prof[i]) * u;
  return Math.sqrt(px * px + py * py + pz * pz) - r;
}

function sTorso(x, y, z, T) {
  const yy = y < T.y0 ? T.y0 : y > T.y1 ? T.y1 : y;
  const f = (yy - T.y0) / T.STEP, i = Math.min(T.n - 2, f | 0), u = f - i;
  const w = T.tw[i] + (T.tw[i + 1] - T.tw[i]) * u, d = T.td[i] + (T.td[i + 1] - T.td[i]) * u;
  const ex = x / w, ez = (z - (T.tz[i] + (T.tz[i + 1] - T.tz[i]) * u)) / d;
  const k0 = Math.sqrt(ex * ex + ez * ez), k1 = Math.sqrt((ex / w) ** 2 + (ez / d) ** 2);
  const de = k1 < 1e-9 ? -Math.min(w, d) : (k0 * (k0 - 1)) / k1;
  return Math.max(de, T.y0 - y, y - T.y1);
}

function smin(a, b, k) {
  const h = Math.max(k - Math.abs(a - b), 0) / k;
  return Math.min(a, b) - h * h * k * 0.25;
}

function boxDist(x, y, z, b) {
  const dx = Math.max(b[0] - x, 0, x - b[3]), dy = Math.max(b[1] - y, 0, y - b[4]), dz = Math.max(b[2] - z, 0, z - b[5]);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

const OUT = { d: 0, comp: 0 };

/** Distancia firmada al cuerpo (negativa adentro). Si `out` se pasa, deja ahí la componente más cercana. */
export function bodySDF(m, x, y, z, out) {
  // tronco + busto/glúteos + cuello + cabeza
  let comp = COMP.torso, best = sTorso(x, y, z, m.torso);
  let T = best;
  for (const e of m.ells) T = smin(T, sEll(x, y, z, e), 0.03);
  const dn = sLimb(x, y, z, m.neck);
  if (dn < best) { best = dn; comp = COMP.neck; }
  T = smin(T, dn, 0.035);
  const dh = smin(sEll(x, y, z, m.head), sEll(x, y, z, m.jaw), 0.03);
  if (dh < best) { best = dh; comp = COMP.head; }
  T = smin(T, dh, 0.025);
  let D = T;

  // extremidades: cada una se funde con el tronco, pero no entre sí
  for (let i = 0; i < 2; i++) {
    const A = m.arms[i];
    if (boxDist(x, y, z, m.bounds.arm[i]) < D) {
      const d1 = sEll(x, y, z, A.delt), d2 = sLimb(x, y, z, A.upper), d3 = sEll(x, y, z, A.elbow), d4 = sLimb(x, y, z, A.fore), d5 = sLimb(x, y, z, A.hand);
      const arm = smin(smin(smin(smin(d1, d2, 0.04), d3, 0.03), d4, 0.03), d5, 0.025);
      const dA = smin(T, arm, 0.03);
      if (dA < D) D = dA;
      const parts = [[d1, COMP.deltoid], [d2, COMP.upperarm], [d3, COMP.forearm], [d4, COMP.forearm], [d5, COMP.hand]];
      for (const [dv, c] of parts) if (dv < best) { best = dv; comp = side(c, A.s); }
    }
    const L = m.legs[i];
    if (boxDist(x, y, z, m.bounds.leg[i]) < D) {
      const d1 = sLimb(x, y, z, L.thigh), d2 = sEll(x, y, z, L.knee), d3 = sLimb(x, y, z, L.calf);
      const d4 = smin(sEll(x, y, z, L.shoe), sEll(x, y, z, L.sole), 0.02);
      const leg = smin(smin(smin(d1, d2, 0.04), d3, 0.04), d4, 0.02);
      const dL = smin(T, leg, 0.045);
      if (dL < D) D = dL;
      const parts = [[d1, COMP.thigh], [d2, COMP.calf], [d3, COMP.calf], [d4, COMP.foot]];
      for (const [dv, c] of parts) if (dv < best) { best = dv; comp = side(c, L.s); }
    }
  }
  D = Math.max(D, -y); // piso
  if (out) { out.d = D; out.comp = comp; }
  return D;
}

/** Solo el tronco (y opcionalmente los deltoides): para medir anillos sin atravesar los brazos. */
export function trunkSDF(m, x, y, z, withDelts = false) {
  let T = sTorso(x, y, z, m.torso);
  for (const e of m.ells) T = smin(T, sEll(x, y, z, e), 0.03);
  T = smin(T, sLimb(x, y, z, m.neck), 0.035);
  if (withDelts) for (const A of m.arms) T = smin(T, sEll(x, y, z, A.delt), 0.04);
  return T;
}

export function gradient(m, x, y, z, e = 0.0007) {
  const gx = bodySDF(m, x + e, y, z) - bodySDF(m, x - e, y, z);
  const gy = bodySDF(m, x, y + e, z) - bodySDF(m, x, y - e, z);
  const gz = bodySDF(m, x, y, z + e) - bodySDF(m, x, y, z - e);
  const l = Math.sqrt(gx * gx + gy * gy + gz * gz) || 1;
  return [gx / l, gy / l, gz / l];
}

// ------------------------------------------------------------------ mallado (surface nets)
/** Malla del cuerpo: vértices proyectados sobre la superficie y normales analíticas (suaves). */
export function meshBody(m, h = 0.0085) {
  const X0 = -0.47, Y0 = -0.012, Z0 = -0.2, X1 = 0.47, Y1 = 1.8, Z1 = 0.22;
  const nx = Math.ceil((X1 - X0) / h) + 1, ny = Math.ceil((Y1 - Y0) / h) + 1, nz = Math.ceil((Z1 - Z0) / h) + 1;
  const field = new Float32Array(nx * ny * nz);
  const id = (i, j, k) => (k * ny + j) * nx + i;
  // banda angosta: se evalúa en bloques de 4³ y solo se refina cerca de la superficie
  const B = 4, far = B * h * 0.9;
  for (let k = 0; k < nz; k += B) for (let j = 0; j < ny; j += B) for (let i = 0; i < nx; i += B) {
    const dc = bodySDF(m, X0 + (i + B / 2) * h, Y0 + (j + B / 2) * h, Z0 + (k + B / 2) * h);
    const exact = Math.abs(dc) < far + h;
    for (let c = k; c < Math.min(nz, k + B); c++) for (let b = j; b < Math.min(ny, j + B); b++) for (let a = i; a < Math.min(nx, i + B); a++) {
      field[id(a, b, c)] = exact ? bodySDF(m, X0 + a * h, Y0 + b * h, Z0 + c * h) : dc;
    }
  }
  // un vértice por celda que cruza la superficie
  const cellVert = new Int32Array((nx - 1) * (ny - 1) * (nz - 1)).fill(-1);
  const cid = (i, j, k) => (k * (ny - 1) + j) * (nx - 1) + i;
  const pos = [];
  const EDGES = [[0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3], [4, 6], [5, 7], [0, 4], [1, 5], [2, 6], [3, 7]];
  const corner = new Float32Array(8);
  for (let k = 0; k < nz - 1; k++) for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
    let mask = 0;
    for (let c = 0; c < 8; c++) {
      const v = field[id(i + (c & 1), j + ((c >> 1) & 1), k + ((c >> 2) & 1))];
      corner[c] = v;
      if (v < 0) mask |= 1 << c;
    }
    if (mask === 0 || mask === 255) continue;
    let sx = 0, sy = 0, sz = 0, cnt = 0;
    for (const [p, q] of EDGES) {
      const a = corner[p], b = corner[q];
      if ((a < 0) === (b < 0)) continue;
      const t = a / (a - b);
      sx += (p & 1) + (((q & 1) - (p & 1)) * t);
      sy += ((p >> 1) & 1) + ((((q >> 1) & 1) - ((p >> 1) & 1)) * t);
      sz += ((p >> 2) & 1) + ((((q >> 2) & 1) - ((p >> 2) & 1)) * t);
      cnt++;
    }
    cellVert[cid(i, j, k)] = pos.length / 3;
    pos.push(X0 + (i + sx / cnt) * h, Y0 + (j + sy / cnt) * h, Z0 + (k + sz / cnt) * h);
  }
  // un quad por arista de la grilla que cruza la superficie
  const idx = [];
  const quad = (a, b, c, d, flip) => {
    if (a < 0 || b < 0 || c < 0 || d < 0) return;
    if (flip) idx.push(a, c, b, a, d, c); else idx.push(a, b, c, a, c, d);
  };
  for (let k = 1; k < nz - 1; k++) for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
    const v0 = field[id(i, j, k)] < 0;
    if (i < nx - 1 && v0 !== (field[id(i + 1, j, k)] < 0)) // arista en x
      quad(cellVert[cid(i, j - 1, k - 1)], cellVert[cid(i, j, k - 1)], cellVert[cid(i, j, k)], cellVert[cid(i, j - 1, k)], !v0);
    if (j < ny - 1 && v0 !== (field[id(i, j + 1, k)] < 0)) // arista en y
      quad(cellVert[cid(i - 1, j, k - 1)], cellVert[cid(i - 1, j, k)], cellVert[cid(i, j, k)], cellVert[cid(i, j, k - 1)], !v0);
    if (k < nz - 1 && v0 !== (field[id(i, j, k + 1)] < 0)) // arista en z
      quad(cellVert[cid(i - 1, j - 1, k)], cellVert[cid(i, j - 1, k)], cellVert[cid(i, j, k)], cellVert[cid(i - 1, j, k)], !v0);
  }
  // proyección sobre la superficie exacta + normales + componente
  const V = pos.length / 3;
  const positions = new Float32Array(pos), normals = new Float32Array(V * 3), comp = new Uint8Array(V);
  const o = { d: 0, comp: 0 };
  for (let v = 0; v < V; v++) {
    let x = positions[v * 3], y = positions[v * 3 + 1], z = positions[v * 3 + 2];
    for (let it = 0; it < 3; it++) {
      const d = bodySDF(m, x, y, z);
      if (Math.abs(d) < 1e-5) break;
      const g = gradient(m, x, y, z);
      x -= g[0] * d; y -= g[1] * d; z -= g[2] * d;
    }
    positions[v * 3] = x; positions[v * 3 + 1] = y; positions[v * 3 + 2] = z;
    const g = gradient(m, x, y, z);
    normals.set(g, v * 3);
    bodySDF(m, x, y, z, o);
    comp[v] = o.comp;
  }
  return { positions, normals, comp, indices: new Uint32Array(idx), vertexCount: V };
}

/** Lleva cada vértice de la malla base a la superficie de otro cuerpo (mismo orden de vértices = morph target). */
export function projectTo(base, mBase, mTarget) {
  const { positions, normals, comp, vertexCount: V } = base;
  const out = new Float32Array(V * 3), nout = new Float32Array(V * 3);
  for (let v = 0; v < V; v++) {
    const [ox, oy, oz] = boneOffset(mBase, mTarget, comp[v], positions[v * 3], positions[v * 3 + 1], positions[v * 3 + 2]);
    const px = positions[v * 3] + ox, py = positions[v * 3 + 1] + oy, pz = positions[v * 3 + 2] + oz;
    const n0 = normals[v * 3], n1 = normals[v * 3 + 1], n2 = normals[v * 3 + 2];
    const f = (t) => bodySDF(mTarget, px + n0 * t, py + n1 * t, pz + n2 * t);
    // secante sobre la normal: la correspondencia de vértices se mantiene estable
    let t0 = 0, f0 = f(0), t1 = -f0, f1 = f(t1);
    for (let it = 0; it < 6 && Math.abs(f1) > 2e-5; it++) {
      const den = f1 - f0;
      if (Math.abs(den) < 1e-9) break;
      const t2 = clamp(t1 - (f1 * (t1 - t0)) / den, -0.12, 0.12);
      t0 = t1; f0 = f1; t1 = t2; f1 = f(t1);
    }
    let x = px + n0 * t1, y = py + n1 * t1, z = pz + n2 * t1;
    let g = gradient(mTarget, x, y, z);
    if (Math.abs(f1) > 1e-3 || g[0] * n0 + g[1] * n1 + g[2] * n2 < 0.2) {
      // cayó en otra superficie (por ejemplo, el otro muslo): se proyecta al punto más cercano
      x = px; y = py; z = pz;
      for (let it = 0; it < 6; it++) {
        const d = bodySDF(mTarget, x, y, z);
        if (Math.abs(d) < 2e-5) break;
        g = gradient(mTarget, x, y, z);
        x -= g[0] * d; y -= g[1] * d; z -= g[2] * d;
      }
      g = gradient(mTarget, x, y, z);
    }
    out[v * 3] = x; out[v * 3 + 1] = y; out[v * 3 + 2] = z;
    nout.set(g, v * 3);
  }
  return { positions: out, normals: nout };
}

/** Desplazamiento inicial de un vértice según cómo se movieron sus articulaciones. */
function boneOffset(mA, mB, c, x, y, z) {
  if (c < COMP.deltoid) {
    if (c === COMP.head) return sub(mB.head.c, mA.head.c);
    return [0, 0, 0];
  }
  const i = c & 1;           // 0 derecho, 1 izquierdo
  const base = c - i;
  const A = mA.arms[i], B = mB.arms[i], LA = mA.legs[i], LB = mB.legs[i];
  const seg = (a0, b0, a1, b1) => {
    const v = sub(b0, a0), l2 = v[0] * v[0] + v[1] * v[1] + v[2] * v[2];
    const t = clamp(((x - a0[0]) * v[0] + (y - a0[1]) * v[1] + (z - a0[2]) * v[2]) / l2, 0, 1);
    const da = sub(a1, a0), db = sub(b1, b0);
    return [da[0] + (db[0] - da[0]) * t, da[1] + (db[1] - da[1]) * t, da[2] + (db[2] - da[2]) * t];
  };
  switch (base) {
    case COMP.deltoid: return sub(B.delt.c, A.delt.c);
    case COMP.upperarm: return seg(A.J, A.E, B.J, B.E);
    case COMP.forearm: return seg(A.E, A.W, B.E, B.W);
    case COMP.hand: return seg(A.W, A.H, B.W, B.H);
    case COMP.thigh: return seg(LA.Hj, LA.K, LB.Hj, LB.K);
    case COMP.calf: return seg(LA.K, LA.A, LB.K, LB.A);
    case COMP.foot: return sub(LB.shoe.c, LA.shoe.c);
    default: return [0, 0, 0];
  }
}
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

// ------------------------------------------------------------------ zonas de medición
const ZONE_OF = {
  [COMP.neck]: () => "neck", [COMP.deltoid]: () => "shoulders",
  [COMP.upperarm]: (s) => `arm_${s}`, [COMP.forearm]: (s) => `forearm_${s}`, [COMP.hand]: () => "wrist",
  [COMP.thigh]: (s) => `thigh_${s}`, [COMP.calf]: (s) => `calf_${s}`,
};
/** Zona de medición de un vértice de la malla base. */
export function zoneOfVertex(c, y) {
  if (c === COMP.torso) return torsoZoneAt(y);
  if (c < COMP.deltoid) return c === COMP.neck ? "neck" : null;
  const i = c & 1, f = ZONE_OF[c - i];
  return f ? f(i === 0 ? "right" : "left") : null;
}

/** Anillos de medición calculados sobre la superficie real: {zona: {pos, r, flat, tilt}}. */
export function measureRings(m) {
  let sdf = (x, y, z) => bodySDF(m, x, y, z);
  const march = (o, dir) => { // del interior hacia afuera hasta la superficie
    let t = 0;
    for (let i = 0; i < 80; i++) {
      const d = sdf(o[0] + dir[0] * t, o[1] + dir[1] * t, o[2] + dir[2] * t);
      if (d > -0.0005 && t > 0.003) break;
      t += Math.max(0.002, Math.abs(d) * 0.8);
    }
    return t;
  };
  const T = m.torso;
  const zAt = (y) => T.tz[Math.round((clamp(y, T.y0, T.y1) - T.y0) / T.STEP)];
  const zones = {};
  const tz = (id, y, k = 1.06) => {
    const c = [0, y, zAt(y)];
    const rx = march(c, [1, 0, 0]), rz = (march(c, [0, 0, 1]) + march(c, [0, 0, -1])) / 2;
    zones[id] = { pos: [0, y, c[2] + (march(c, [0, 0, 1]) - march(c, [0, 0, -1])) / 2], r: rx * k, flat: rz / rx, tilt: 0 };
  };
  sdf = (x, y, z) => trunkSDF(m, x, y, z, true);
  tz("shoulders", 1.395, 1.05);
  sdf = (x, y, z) => trunkSDF(m, x, y, z);
  tz("neck", 1.535, 1.12);
  tz("chest", m.F ? 1.272 : 1.3);
  tz("waist", 1.1);
  tz("abdomen", 1.03);
  tz("hip", m.F ? 0.915 : 0.905, 1.07);
  sdf = (x, y, z) => bodySDF(m, x, y, z);
  const limbRing = (id, a, b, t, k = 1.15) => {
    const c = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const out = [-dy * Math.sign(c[0] || 1), dx * Math.sign(c[0] || 1), 0];
    const l = Math.hypot(out[0], out[1]) || 1;
    const r = (march(c, [Math.abs(out[0] / l) * Math.sign(c[0] || 1), out[1] / l * 0, 0]) + march(c, [0, 0, 1])) / 2;
    zones[id] = { pos: c, r: r * k, flat: 1, tilt: Math.atan2(dx, -dy) };
  };
  for (const A of m.arms) {
    const s = A.s < 0 ? "right" : "left";
    limbRing(`arm_${s}`, A.J, A.E, 0.45);
    limbRing(`forearm_${s}`, A.E, A.W, 0.22);
    if (A.s < 0) limbRing("wrist", A.E, A.W, 0.97, 1.3);
  }
  for (const L of m.legs) {
    const s = L.s < 0 ? "right" : "left";
    limbRing(`thigh_${s}`, L.Hj, L.K, 0.32);
    limbRing(`calf_${s}`, L.K, L.A, 0.3);
  }
  return zones;
}
