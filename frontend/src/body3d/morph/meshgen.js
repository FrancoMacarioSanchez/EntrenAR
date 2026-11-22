// Generación de la malla del avatar SIN Three.js (corre en un Web Worker y en Node para tests).
// Convierte las piezas de avatarSpec en un único buffer indexado con topología estable.

export const SLOTS = ["skin", "top", "bottom", "shoe", "sole", "hair", "eye", "brow", "lips", "chest", "shoulder"];
export const ZONE_IDS = [null, "torso", "neck", "shoulders", "chest", "waist", "abdomen", "hip", "arm_right", "arm_left",
  "forearm_right", "forearm_left", "wrist", "thigh_right", "thigh_left", "calf_right", "calf_left"];

// resolución por tamaño de pieza (las chicas no necesitan tantos vértices)
function sphereSegs(r) {
  const m = Math.max(r[0], r[1], r[2]);
  return m < 0.03 ? [12, 8] : m < 0.07 ? [20, 14] : [28, 18];
}

// ---------------------------------------------------------------- primitivas (mismo orden que Three.js)
function sphere(wS, hS, theta = Math.PI) {
  const pos = [], idx = [];
  const grid = [];
  for (let iy = 0; iy <= hS; iy++) {
    const row = [], v = iy / hS;
    for (let ix = 0; ix <= wS; ix++) {
      const u = ix / wS;
      pos.push(-Math.cos(u * Math.PI * 2) * Math.sin(v * theta), Math.cos(v * theta), Math.sin(u * Math.PI * 2) * Math.sin(v * theta));
      row.push(pos.length / 3 - 1);
    }
    grid.push(row);
  }
  for (let iy = 0; iy < hS; iy++) {
    for (let ix = 0; ix < wS; ix++) {
      const a = grid[iy][ix + 1], b = grid[iy][ix], c = grid[iy + 1][ix], d = grid[iy + 1][ix + 1];
      if (iy !== 0) idx.push(a, b, d);
      if (iy !== hS - 1 || theta < Math.PI) idx.push(b, c, d);
    }
  }
  return { pos, idx };
}

function lathe(points, segs = 32) {
  const pos = [], idx = [];
  for (let i = 0; i <= segs; i++) {
    const phi = (i / segs) * Math.PI * 2, s = Math.sin(phi), c = Math.cos(phi);
    for (const [r, y] of points) pos.push(r * s, y, r * c);
  }
  const n = points.length;
  for (let i = 0; i < segs; i++) {
    for (let j = 0; j < n - 1; j++) {
      const base = j + i * n, a = base, b = base + n, c = base + n + 1, d = base + 1;
      idx.push(a, b, d, c, d, b);
    }
  }
  return { pos, idx };
}

function loft(rows, open, seg = 40) {
  const pos = [], idx = [];
  for (const r of rows) {
    for (let i = 0; i <= seg; i++) {
      const a = (i / seg) * Math.PI * 2;
      pos.push(Math.cos(a) * r.w, r.y, r.dz + Math.sin(a) * r.d);
    }
  }
  const L = seg + 1;
  for (let j = 0; j < rows.length - 1; j++) {
    for (let i = 0; i < seg; i++) {
      const a = j * L + i, b = a + L;
      idx.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  if (!open) {
    for (const [j, bottom] of [[0, true], [rows.length - 1, false]]) {
      const c = pos.length / 3;
      pos.push(0, rows[j].y, rows[j].dz);
      for (let i = 0; i < seg; i++) {
        const a = j * L + i;
        if (bottom) idx.push(c, a, a + 1); else idx.push(c, a + 1, a);
      }
    }
  }
  return { pos, idx };
}

// ---------------------------------------------------------------- transformaciones
function eulerXYZ([x, y, z]) {
  const a = Math.cos(x), b = Math.sin(x), c = Math.cos(y), d = Math.sin(y), e = Math.cos(z), f = Math.sin(z);
  const ae = a * e, af = a * f, be = b * e, bf = b * f;
  return [c * e, -c * f, d, af + be * d, ae - bf * d, -b * c, bf - ae * d, be + af * d, a * c];
}

function alignY(dir) {
  // matriz de rotación que lleva (0,1,0) a dir (unitario). Fórmula de Rodrigues con eje e_y × dir.
  const [x, y, z] = dir;
  if (y < -0.999999) return [1, 0, 0, 0, -1, 0, 0, 0, -1];
  const k = 1 / (1 + y);
  // eje v = (z, 0, -x), c = y
  return [
    1 - x * x * k, x, -x * z * k,
    -x, y, -z,
    -x * z * k, z, 1 - z * z * k,
  ];
}

function apply(pos, m, t) {
  for (let i = 0; i < pos.length; i += 3) {
    const x = pos[i], y = pos[i + 1], z = pos[i + 2];
    pos[i] = m[0] * x + m[1] * y + m[2] * z + t[0];
    pos[i + 1] = m[3] * x + m[4] * y + m[5] * z + t[1];
    pos[i + 2] = m[6] * x + m[7] * y + m[8] * z + t[2];
  }
}

function partGeometry(p, segs) {
  if (p.type === "loft") return loft(p.rows, p.open);
  if (p.type === "ellipsoid" || p.type === "cap") {
    const [w, h] = segs || sphereSegs(p.r);
    const g = p.type === "cap" ? sphere(36, 16, p.theta) : sphere(w, h);
    for (let i = 0; i < g.pos.length; i += 3) { g.pos[i] *= p.r[0]; g.pos[i + 1] *= p.r[1]; g.pos[i + 2] *= p.r[2]; }
    apply(g.pos, p.rot ? eulerXYZ(p.rot) : [1, 0, 0, 0, 1, 0, 0, 0, 1], p.pos);
    return g;
  }
  if (p.type === "lathe") {
    const d = [p.to[0] - p.from[0], p.to[1] - p.from[1], p.to[2] - p.from[2]];
    const len = Math.hypot(...d) || 1e-6;
    const n = p.profile.length;
    const pts = p.profile.map((r, i) => [r, (i / (n - 1)) * len]);
    if (!p.open) { pts.unshift([0.0005, 0]); pts.push([0.0005, len]); }
    const g = lathe(pts, 28);
    if (p.flatten) for (let i = 2; i < g.pos.length; i += 3) g.pos[i] *= p.flatten;
    apply(g.pos, alignY(d.map((v) => v / len)), p.from);
    return g;
  }
  return null;
}

/**
 * Une todas las piezas en un buffer. Devuelve posiciones, índices, slot de color y zona por vértice.
 * `layout` fija la resolución de cada pieza (se toma de la malla base para que los targets tengan la misma topología).
 */
export function specToBuffers(spec, layout) {
  const chunks = [];
  const usedLayout = [];
  let nv = 0, ni = 0;
  for (const [i, p] of spec.parts.entries()) {
    const segs = layout ? layout[i] : (p.type === "ellipsoid" ? sphereSegs(p.r) : null);
    usedLayout.push(segs);
    const g = partGeometry(p, segs);
    if (!g) continue;
    chunks.push({ g, slot: Math.max(0, SLOTS.indexOf(p.type === "cap" ? "hair" : p.mat)), zone: Math.max(0, ZONE_IDS.indexOf(p.zone || null)) });
    nv += g.pos.length / 3;
    ni += g.idx.length;
  }
  const positions = new Float32Array(nv * 3), indices = new Uint32Array(ni);
  const slots = new Uint8Array(nv), zones = new Uint8Array(nv);
  let vo = 0, io = 0;
  for (const { g, slot, zone } of chunks) {
    positions.set(g.pos, vo * 3);
    for (let i = 0; i < g.idx.length; i++) indices[io + i] = g.idx[i] + vo;
    const n = g.pos.length / 3;
    slots.fill(slot, vo, vo + n);
    zones.fill(zone, vo, vo + n);
    vo += n;
    io += g.idx.length;
  }
  return { positions, indices, slots, zones, vertexCount: nv, layout: usedLayout };
}


/** Normales por vértice (promedio de caras) para la malla base y cada target. */
export function computeNormals(positions, indices) {
  const n = new Float32Array(positions.length);
  for (let t = 0; t < indices.length; t += 3) {
    const a = indices[t] * 3, b = indices[t + 1] * 3, c = indices[t + 2] * 3;
    const ux = positions[b] - positions[a], uy = positions[b + 1] - positions[a + 1], uz = positions[b + 2] - positions[a + 2];
    const vx = positions[c] - positions[a], vy = positions[c + 1] - positions[a + 1], vz = positions[c + 2] - positions[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const k of [a, b, c]) { n[k] += nx; n[k + 1] += ny; n[k + 2] += nz; }
  }
  for (let i = 0; i < n.length; i += 3) {
    const l = Math.hypot(n[i], n[i + 1], n[i + 2]) || 1;
    n[i] /= l; n[i + 1] /= l; n[i + 2] /= l;
  }
  return n;
}
