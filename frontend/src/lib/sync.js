// Cola offline: las sesiones de entrenamiento y mediciones se guardan primero en el teléfono
// y se envían al servidor cuando hay conexión (idempotente por client_uuid).
import { api } from "./api";
import { outbox } from "./db";

const listeners = new Set();
export function onSync(fn) { listeners.add(fn); return () => listeners.delete(fn); }
function emit(e) { listeners.forEach((fn) => fn(e)); }

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
}

export async function enqueue(type, payload) {
  const op = { id: payload.client_uuid || uuid(), type, payload, created: Date.now() };
  await outbox.put(op);
  emit({ type: "queued", op });
  return flush();
}

let running = null;
let dirty = false;
export function flush() {
  if (running) { dirty = true; return running; }
  running = (async () => {
    const ops = await outbox.all();
    if (!ops.length) return { results: [] };
    if (!navigator.onLine) { emit({ type: "pending", count: ops.length }); return { offline: true, results: [] }; }
    try {
      const res = await api("/me/sync/", { method: "POST", body: { ops } });
      const rejected = [];
      for (const r of res.results) {
        if (r.ok) await outbox.del(r.id);
        else if (r.fatal) { await outbox.del(r.id); rejected.push(r); } // datos inválidos: no reintentar
      }
      emit({ type: "synced", results: res.results, count: await outbox.count() });
      if (rejected.length) emit({ type: "rejected", results: rejected });
      return res;
    } catch (e) {
      emit({ type: "error", error: e, count: ops.length });
      return { error: e, results: [] };
    }
  })().finally(() => {
    running = null;
    if (dirty) { dirty = false; setTimeout(() => flush(), 50); }
  });
  return running;
}

export const pendingCount = () => outbox.count();

if (typeof window !== "undefined") {
  window.addEventListener("online", () => flush());
  setInterval(() => flush(), 60000);
}
