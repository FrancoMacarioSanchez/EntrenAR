// Motor de avatares con morph targets (shape keys) sobre una única malla base continua.
//  - El cuerpo se genera una vez por dispositivo en un Web Worker (y queda guardado en IndexedDB).
//  - Sexo, musculatura, grasa, medidas y moldeado solo mueven pesos (morphTargetInfluences, en la GPU).
//  - Las normales se recalculan en la CPU cuando cambian los pesos (unos milisegundos): sombreado limpio.
//  - La ropa se pinta por vértice y el pelo depende solo del peinado: cambiar de prenda no regenera nada.
//  - Si existe un modelo GLB con shape keys (VITE_AVATAR_GLB), se usa ese con los mismos nombres de targets.
import * as THREE from "three";
import { BODY_ONLY, buildSpec, girthFactors, normalizeAvatar, REGIONS, torsoZoneAt } from "../avatarSpec";
import { computeNormals, SLOTS, ZONE_IDS } from "./meshgen";
import { bodyModel, measureRings } from "./sdfBody";
import { computeWeights, generateMorphData, morphPositions, MORPH_TARGETS, paintSlots, REGION_STEP, regionOfZone, styleKey } from "./targets";

const cache = new Map();
let worker; // undefined = no creado · null = no disponible
let seq = 0;
const pending = new Map();

function getWorker() {
  if (worker !== undefined) return worker;
  try {
    worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
    worker.onmessage = (e) => {
      const p = pending.get(e.data.id);
      if (!p) return;
      pending.delete(e.data.id);
      if (e.data.error) p.reject(new Error(e.data.error)); else p.resolve(e.data.data);
    };
    worker.onerror = () => {
      worker = null;
      for (const p of pending.values()) p.fallback();
      pending.clear();
    };
  } catch {
    worker = null;
  }
  return worker;
}

/** Malla + targets para un peinado (con caché en memoria; el cuerpo queda en IndexedDB). */
export function loadMorphData(style) {
  const key = styleKey(style);
  if (!cache.has(key)) {
    cache.set(key, (async () => {
      const w = getWorker();
      if (w) {
        try {
          return await new Promise((resolve, reject) => {
            const id = ++seq;
            pending.set(id, { resolve, reject, fallback: () => resolve(generateMorphData(style)) });
            w.postMessage({ id, style: { hair_style: style.hair_style } });
          });
        } catch (e) {
          console.warn("Worker de avatar falló, genero en el hilo principal:", e);
        }
      }
      return generateMorphData(style);
    })());
  }
  return cache.get(key);
}

function geometryFrom(d) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(d.positions, 3));
  g.setAttribute("normal", new THREE.BufferAttribute(Float32Array.from(d.normals), 3).setUsage(THREE.DynamicDrawUsage));
  g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(d.vertexCount * 3), 3));
  g.setIndex(new THREE.BufferAttribute(d.indices, 1));
  g.morphAttributes.position = d.targets.map((t) => Object.assign(new THREE.BufferAttribute(t.delta, 3), { name: t.name }));
  g.morphTargetsRelative = true;
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.9, 0), 1.2); // fijo: los morph no lo actualizan
  return g;
}

/** Factores de perímetro efectivos (medidas + moldeado), coherentes con los pesos. */
export function effectiveFactors(weights) {
  return Object.fromEntries(REGIONS.map((r) => [r, Math.max(0.6, 1 + (weights[`girth_${r}`] || 0) * REGION_STEP)]));
}

export class AvatarEngine {
  /** externalUrl: modelo GLB con shape keys (si falla se usa el cuerpo generado por código). */
  constructor(root, { externalUrl } = {}) {
    this.root = root;
    this.mesh = null;
    this.data = null;
    this.style = null;
    this.target = {};
    this.avatar = null;
    this.colors = null;
    this.scale = 1;
    this.token = 0;
    this.slots = null;
    this.paintKey = "";
    this.highlight = null;
    this.normalsDirty = true;
    this.normalsAt = 0;
    this.morphBuf = null;
    this.material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.58, metalness: 0 });
    this.external = null;
    this.ready = externalUrl
      ? this.loadExternal(externalUrl).catch((e) => { console.warn("Uso el avatar generado por código:", e.message); return false; })
      : Promise.resolve(false);
  }

  /** Aplica una configuración. Solo regenera la malla si cambió el peinado. */
  async update(avatar, measures) {
    await this.ready;
    let a = normalizeAvatar(avatar);
    if (BODY_ONLY) a = { ...a, hair_style: "bald" };
    const spec = buildSpec(a, measures); // liviano: colores y escala
    this.avatar = a;
    // con un modelo propio, las medidas se comparan contra SUS perímetros (hombre o mujer)
    this.target = computeWeights(a, measures, this.external?.reference?.[a.sex]);
    this.colors = spec.colors;
    this.scale = spec.scale;
    this.root.scale.setScalar(spec.scale);
    this.normalsDirty = true;
    const key = styleKey(a);
    if (!this.external && key !== this.style) {
      const token = ++this.token;
      const d = await loadMorphData(a);
      if (token !== this.token) return spec; // llegó una configuración más nueva
      this._setMesh(d, key);
    }
    this.recolor();
    return spec;
  }

  /** Pesos objetivo directos (moldeado en vivo, sin pasar por React). */
  setWeight(name, value) {
    this.target = { ...this.target, [name]: value };
    this.normalsDirty = true;
  }

  /** Anillos de medición sobre la superficie real, con los pesos actuales. */
  rings() {
    if (!this.avatar) return {};
    const R = this.external?.rings;
    if (R) { // anillos medidos sobre el modelo, combinados con los mismos pesos que los shape keys
      const out = {};
      for (const [z, base] of Object.entries(R.base)) {
        const v = [...base];
        for (const [name, w] of Object.entries(this.target)) {
          const d = R.delta[name]?.[z];
          if (d && w) for (let i = 0; i < 6; i++) v[i] += d[i] * w;
        }
        out[z] = { pos: v.slice(0, 3), r: Math.max(0.01, v[3]), flat: v[4], tilt: v[5] };
      }
      return out;
    }
    return measureRings(bodyModel(this.avatar, effectiveFactors(this.target)));
  }

  _setMesh(d, key) {
    const prev = this.mesh ? this._influences() : null;
    if (this.mesh) { this.root.remove(this.mesh); this.mesh.geometry.dispose(); }
    this.data = d;
    this.style = key;
    this.paintKey = "";
    this.slots = null;
    this.morphBuf = new Float32Array(d.positions.length);
    this.mesh = new THREE.Mesh(geometryFrom(d), this.material);
    this.mesh.userData.avatar = true;
    // arranca desde los pesos anteriores (o los finales) para que la transición sea suave
    for (const [name, i] of Object.entries(this.mesh.morphTargetDictionary)) {
      this.mesh.morphTargetInfluences[i] = prev?.[name] ?? this.target[name] ?? 0;
    }
    this.normalsDirty = true;
    this._updateNormals();
    this.root.add(this.mesh);
  }

  _influences() {
    const m = this.mesh;
    return Object.fromEntries(Object.entries(m.morphTargetDictionary).map(([n, i]) => [n, m.morphTargetInfluences[i]]));
  }

  _updateNormals() {
    if (!this.mesh) return;
    const P = morphPositions(this.data, this._influences(), this.morphBuf);
    const attr = this.mesh.geometry.getAttribute("normal");
    attr.array.set(computeNormals(P, this.data.indices));
    attr.needsUpdate = true;
    this.normalsDirty = false;
  }

  /** Resalta una región moldeable (o null). */
  setHighlight(region) {
    if (region === this.highlight) return;
    this.highlight = region;
    this.recolor();
  }

  _tint() {
    return new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue("--brand").trim() || "#ff5a1f");
  }

  recolor() {
    if (this.external) return this._recolorExternal();
    if (!this.mesh || !this.colors) return;
    const a = this.avatar;
    const pk = `${a.sex}|${a.top_style}|${a.bottom_style}`;
    if (pk !== this.paintKey) { this.slots = paintSlots(this.data, a, this.slots); this.paintKey = pk; }
    const c = new THREE.Color();
    const table = SLOTS.map((s) => {
      let hex = this.colors[s];
      if (this.colors[hex]) hex = this.colors[hex];
      c.set(hex || "#888888");
      return [c.r, c.g, c.b];
    });
    const hl = this.highlight;
    const hlZones = hl ? new Set(ZONE_IDS.map((z, i) => (regionOfZone(z) === hl ? i : -1)).filter((i) => i >= 0)) : null;
    const tint = this._tint();
    const attr = this.mesh.geometry.getAttribute("color");
    const { zones } = this.data, slots = this.slots, bodyN = this.data.bodyVertexCount;
    for (let i = 0; i < slots.length; i++) {
      let [r, g, b] = table[slots[i]];
      if (hlZones && i < bodyN && hlZones.has(zones[i])) {
        r = r * 0.55 + tint.r * 0.45; g = g * 0.55 + tint.g * 0.45; b = b * 0.55 + tint.b * 0.45;
      }
      attr.array[i * 3] = r; attr.array[i * 3 + 1] = g; attr.array[i * 3 + 2] = b;
    }
    attr.needsUpdate = true;
  }

  /** Interpola los pesos hacia el objetivo (llamar en cada frame). */
  tick(dt, now = performance.now()) {
    const list = this.external ? this.external.meshes : this.mesh ? [this.mesh] : [];
    const k = Math.min(1, dt * 9);
    let moving = false;
    for (const m of list) {
      if (!m.morphTargetInfluences) continue;
      for (const [name, i] of Object.entries(m.morphTargetDictionary)) {
        const t = this.target[name] ?? 0;
        const cur = m.morphTargetInfluences[i];
        if (Math.abs(t - cur) > 1e-4) { m.morphTargetInfluences[i] = cur + (t - cur) * k; moving = true; }
        else m.morphTargetInfluences[i] = t;
      }
    }
    if (!this.external && !this.mesh) return;
    // normales: durante la animación cada ~90 ms, y una vez al terminar
    if (this.normalsDirty && (!moving || now - this.normalsAt > 90)) {
      this.normalsAt = now;
      if (this.external) this._externalNormals(); else this._updateNormals();
      if (moving) this.normalsDirty = true;
    }
  }

  /** Zona de medición tocada. */
  zoneFromHit(hit) {
    if (this.external) return hit.object === this.external.mesh ? this._externalZone(hit) : null;
    if (!this.data || hit.object !== this.mesh) return null;
    const i = hit.face.a;
    if (i >= this.data.bodyVertexCount) return null;
    return ZONE_IDS[this.data.zones[i]];
  }

  get pickTargets() { return this.mesh ? [this.mesh] : this.external ? [this.external.mesh] : []; }

  // ------------------------------------------------------------ modelo externo (opcional)
  async loadExternal(url) {
    const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
    const gltf = await new GLTFLoader().loadAsync(url);
    const meshes = [];
    gltf.scene.traverse((o) => { if (o.isMesh && o.morphTargetDictionary) meshes.push(o); });
    // el cuerpo es el objeto llamado "body" (o el de más vértices); la ropa y el pelo comparten los mismos shape keys
    const mesh = meshes.find((o) => /^body/i.test(o.name))
      || meshes.sort((x, y) => y.geometry.attributes.position.count - x.geometry.attributes.position.count)[0];
    if (!mesh) throw new Error("El GLB no tiene shape keys");
    const missing = MORPH_TARGETS.map((t) => t.name).filter((n) => !(n in mesh.morphTargetDictionary));
    if (missing.length) console.warn("Shape keys faltantes en el GLB:", missing.join(", "));
    this.token++;
    if (this.mesh) { this.root.remove(this.mesh); this.mesh.geometry.dispose(); this.mesh = null; }
    for (const o of meshes) o.frustumCulled = false; // los morph agrandan la malla más allá de su caja original
    this.external = { scene: gltf.scene, mesh, meshes, rings: mesh.userData.rings, reference: mesh.userData.reference_cm };
    this.normalsDirty = true;
    this.root.add(gltf.scene);
    this._recolorExternal();
    return true;
  }

  /** GLB sin normales de morph (más liviano): se recalculan en la CPU, solo para los objetos visibles. */
  _externalNormals() {
    for (const m of this.external.meshes) {
      const g = m.geometry;
      if (!m.visible || g.morphAttributes.normal?.length) continue;
      let c = m.userData.cpuNormals;
      if (!c) {
        const pos = g.getAttribute("position");
        const n = pos.count * 3;
        const toF32 = (attr) => { const a = new Float32Array(n); for (let i = 0; i < pos.count; i++) { a[i * 3] = attr.getX(i); a[i * 3 + 1] = attr.getY(i); a[i * 3 + 2] = attr.getZ(i); } return a; };
        const idx = g.index ? Uint32Array.from(g.index.array) : Uint32Array.from({ length: pos.count }, (_, i) => i);
        c = m.userData.cpuNormals = { base: toF32(pos), targets: (g.morphAttributes.position || []).map(toF32), idx, buf: new Float32Array(n) };
        g.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(n), 3));
      }
      const P = c.buf;
      P.set(c.base);
      c.targets.forEach((d, t) => {
        const w = m.morphTargetInfluences[t];
        if (Math.abs(w) < 1e-4) return;
        for (let i = 0; i < P.length; i++) P[i] += d[i] * w;
      });
      const attr = g.getAttribute("normal");
      attr.array.set(computeNormals(P, c.idx));
      attr.needsUpdate = true;
    }
  }

  _externalZone(hit) {
    // 1) atributo de vértice _ZONE (índice de ZONE_IDS) exportado desde Blender
    const za = hit.object.geometry.getAttribute("_zone");
    if (za) return ZONE_IDS[Math.round(za.getX(hit.face.a))] || null;
    // 2) aproximación por posición
    const p = this.root.worldToLocal(hit.point.clone()); // metros del cuerpo base (sin la escala por altura)
    const side = p.x < 0 ? "right" : "left", ax = Math.abs(p.x);
    if (p.y < 0.86) return p.y > 0.49 ? `thigh_${side}` : p.y > 0.1 ? `calf_${side}` : null;
    if (ax > 0.2 && p.y < 1.36) return p.y > 1.13 ? `arm_${side}` : p.y > 0.9 ? `forearm_${side}` : "wrist";
    return p.y > 1.6 ? null : torsoZoneAt(p.y);
  }

  _recolorExternal() {
    if (!this.external || !this.colors) return;
    const body = this.external.mesh, za = body.geometry.getAttribute("_zone");
    if (za) {
      const g = body.geometry, n = g.getAttribute("position").count;
      if (!g.getAttribute("color")) g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
      const mats = Array.isArray(body.material) ? body.material : [body.material];
      for (const m of mats) if (!m.vertexColors) { m.vertexColors = true; m.color.set("#ffffff"); m.needsUpdate = true; }
      const skin = new THREE.Color(this.colors.skin), tint = this._tint(), hl = this.highlight;
      const hlZones = hl ? new Set(ZONE_IDS.map((z, i) => (regionOfZone(z) === hl ? i : -1)).filter((i) => i >= 0)) : null;
      const col = g.getAttribute("color");
      for (let i = 0; i < n; i++) {
        const on = hlZones?.has(Math.round(za.getX(i)));
        col.array[i * 3] = on ? skin.r * 0.55 + tint.r * 0.45 : skin.r;
        col.array[i * 3 + 1] = on ? skin.g * 0.55 + tint.g * 0.45 : skin.g;
        col.array[i * 3 + 2] = on ? skin.b * 0.55 + tint.b * 0.45 : skin.b;
      }
      col.needsUpdate = true;
    }
    this.external.scene.traverse((o) => {
      if (!o.isMesh) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        const key = (m.name || "").toLowerCase().split(/[^a-z]/)[0]; // "skin", "top", "bottom", "hair", "shoe"…
        if (m.vertexColors) continue; // el cuerpo ya se pintó por vértice
        let hex = this.colors[key];
        if (this.colors[hex]) hex = this.colors[hex];
        if (hex && m.color) m.color.set(hex);
      }
    });
    // prendas como objetos separados: se muestran solo las del estilo elegido (top_tank, bottom_shorts, hair_bun…)
    const a = this.avatar;
    if (!a) return;
    this.external.scene.traverse((o) => {
      const mm = /^(top|bottom|hair)_([a-z]+)$/.exec((o.name || "").toLowerCase());
      if (mm) o.visible = a[`${mm[1]}_style`] === mm[2];
    });
    this.normalsDirty = true;
  }

  dispose() {
    this.token++;
    if (this.mesh) { this.root.remove(this.mesh); this.mesh.geometry.dispose(); }
    if (this.external) this.root.remove(this.external.scene);
    this.material.dispose();
  }
}

export { girthFactors, regionOfZone };
