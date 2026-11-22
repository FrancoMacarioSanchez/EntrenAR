// Cliente de la API con JWT (el token está atado al gimnasio en el backend).
const BASE = "/api/v1";
const KEY = "entrenar.auth";

export function getTokens() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
}
export function setTokens(t) {
  if (t) localStorage.setItem(KEY, JSON.stringify(t)); else localStorage.removeItem(KEY);
}

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

let refreshing = null;
async function refresh() {
  const t = getTokens();
  if (!t?.refresh) throw new ApiError("Sesión vencida", 401);
  if (!refreshing) {
    refreshing = fetch(`${BASE}/auth/refresh/`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh: t.refresh }),
    }).then(async (r) => {
      if (!r.ok) { setTokens(null); throw new ApiError("Sesión vencida", 401); }
      const d = await r.json();
      setTokens({ access: d.access, refresh: d.refresh || t.refresh });
    }).finally(() => { refreshing = null; });
  }
  return refreshing;
}

export async function api(path, { method = "GET", body, form, retry = true, signal } = {}) {
  const t = getTokens();
  const headers = {};
  if (t?.access) headers.Authorization = `Bearer ${t.access}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: payload, signal });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError("Sin conexión", 0);
  }
  if (res.status === 401 && retry && t?.refresh) {
    await refresh();
    return api(path, { method, body, form, retry: false, signal });
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || data.non_field_errors?.[0] || Object.values(data)[0]?.[0] || "Error inesperado";
    throw new ApiError(typeof msg === "string" ? msg : "Error inesperado", res.status, data);
  }
  return data;
}

export const get = (p, o) => api(p, o);
export const post = (p, body) => api(p, { method: "POST", body });
export const put = (p, body) => api(p, { method: "PUT", body });
export const del = (p) => api(p, { method: "DELETE" });

export async function login(username, password) {
  const r = await fetch(`${BASE}/auth/token/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 404) throw new ApiError(d.detail || `No hay ningún gimnasio en «${location.hostname}». Entrá con el subdominio del gimnasio, por ejemplo demo.localhost.`, 404);
    throw new ApiError(r.status === 401 ? "Usuario o contraseña incorrectos" : (d.detail || "No se pudo ingresar"), r.status);
  }
  setTokens({ access: d.access, refresh: d.refresh });
}
