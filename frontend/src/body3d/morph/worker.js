// Web Worker: genera el cuerpo (una vez por dispositivo, se guarda en IndexedDB) y la malla de cada peinado.
import { buildBody, generateMorphData, getBodyCache, MESH_VERSION, setBodyCache } from "./targets.js";

const DB = "entrenar-avatar", STORE = "mesh", KEY = `body-v${MESH_VERSION}`;

function idb() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE);
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
async function idbGet() {
  const db = await idb();
  return new Promise((resolve) => {
    const q = db.transaction(STORE).objectStore(STORE).get(KEY);
    q.onsuccess = () => resolve(q.result || null);
    q.onerror = () => resolve(null);
  });
}
async function idbPut(value) {
  const db = await idb();
  const tx = db.transaction(STORE, "readwrite");
  const st = tx.objectStore(STORE);
  st.clear(); // borra versiones viejas
  st.put(value, KEY);
}

let ready = null;
function ensureBody() {
  ready ||= (async () => {
    if (getBodyCache()) return;
    try {
      const cached = await idbGet();
      if (cached?.version === MESH_VERSION) { setBodyCache(cached); return; }
    } catch { /* sin IndexedDB: se genera igual */ }
    const body = buildBody();
    setBodyCache(body);
    try { await idbPut(body); } catch { /* sin espacio: no pasa nada */ }
  })();
  return ready;
}

self.onmessage = async (e) => {
  const { id, style } = e.data;
  try {
    await ensureBody();
    const d = generateMorphData(style);
    const transfer = [d.positions.buffer, d.normals.buffer, d.indices.buffer, d.comp.buffer, d.fixedSlots.buffer, d.zones.buffer];
    for (const t of d.targets) transfer.push(t.delta.buffer);
    self.postMessage({ id, data: d }, transfer);
  } catch (err) {
    self.postMessage({ id, error: String(err?.message || err) });
  }
};
