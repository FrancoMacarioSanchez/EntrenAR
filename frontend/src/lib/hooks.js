import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { kv } from "./db";

// useApi: trae datos y los cachea en IndexedDB para mostrarlos sin conexión.
export function useApi(path, { cache = true, deps = [] } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [stale, setStale] = useState(false);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      const d = await api(path);
      if (!alive.current) return;
      setData(d); setError(null); setStale(false);
      if (cache) kv.set("cache:" + path, d).catch(() => {});
    } catch (e) {
      if (!alive.current) return;
      if (cache) {
        const c = await kv.get("cache:" + path).catch(() => null);
        if (c) { setData(c); setStale(true); setError(null); setLoading(false); return; }
      }
      setError(e);
    } finally { if (alive.current) setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);

  useEffect(() => {
    alive.current = true;
    if (cache && path) kv.get("cache:" + path).then((c) => { if (c && alive.current) setData((d) => d || c); }).catch(() => {});
    load();
    return () => { alive.current = false; };
  }, [load]);

  return { data, error, loading, stale, reload: load, setData };
}

export function useOnline() {
  const [on, setOn] = useState(navigator.onLine);
  useEffect(() => {
    const a = () => setOn(true), b = () => setOn(false);
    window.addEventListener("online", a); window.addEventListener("offline", b);
    return () => { window.removeEventListener("online", a); window.removeEventListener("offline", b); };
  }, []);
  return on;
}
