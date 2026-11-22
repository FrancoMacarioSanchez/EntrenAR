// IndexedDB mínimo: un almacén clave/valor y una cola "outbox" para trabajar sin conexión.
const DB_NAME = "entrenar";
const VERSION = 1;
let dbp;

function open() {
  if (dbp) return dbp;
  dbp = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("kv")) db.createObjectStore("kv");
      if (!db.objectStoreNames.contains("outbox")) db.createObjectStore("outbox", { keyPath: "id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbp;
}

function tx(store, mode, fn) {
  return open().then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const s = t.objectStore(store);
    const r = fn(s);
    t.oncomplete = () => resolve(r && "result" in r ? r.result : undefined);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  }));
}

export const kv = {
  get: (k) => tx("kv", "readonly", (s) => s.get(k)),
  set: (k, v) => tx("kv", "readwrite", (s) => s.put(v, k)),
  del: (k) => tx("kv", "readwrite", (s) => s.delete(k)),
};

export const outbox = {
  all: () => tx("outbox", "readonly", (s) => s.getAll()),
  put: (op) => tx("outbox", "readwrite", (s) => s.put(op)),
  del: (id) => tx("outbox", "readwrite", (s) => s.delete(id)),
  count: () => tx("outbox", "readonly", (s) => s.count()),
};

export async function clearAll() {
  const db = await open();
  await Promise.all(["kv", "outbox"].map((n) => new Promise((res) => {
    const t = db.transaction(n, "readwrite"); t.objectStore(n).clear(); t.oncomplete = res;
  })));
}
