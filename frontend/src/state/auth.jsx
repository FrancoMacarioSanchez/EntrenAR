import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getTokens, login as apiLogin, setTokens } from "../lib/api";
import { clearAll, kv } from "../lib/db";
import { flush } from "../lib/sync";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

function applyBrand(gym) {
  if (!gym) return;
  const c = gym.primary_color || "#ff5a1f";
  document.documentElement.style.setProperty("--brand", c);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", c);
  document.title = gym.name || "EntrenAR";
}

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null);
  const [ready, setReady] = useState(false);
  const [gym, setGym] = useState(null);

  const loadMe = useCallback(async () => {
    try {
      const d = await api("/me/");
      setMe(d); applyBrand(d.gym); setGym(d.gym);
      kv.set("me", d).catch(() => {});
      return d;
    } catch (e) {
      if (e.status === 401) { setTokens(null); setMe(null); return null; }
      const cached = await kv.get("me").catch(() => null); // sin conexión: usamos lo último
      if (cached) { setMe(cached); applyBrand(cached.gym); setGym(cached.gym); }
      return cached;
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (getTokens()) { await loadMe(); flush(); }
      else {
        try { const d = await api("/auth/info/"); setGym(d.gym); applyBrand(d.gym); } catch { /* offline */ }
      }
      setReady(true);
    })();
  }, [loadMe]);

  const login = async (u, p) => { await apiLogin(u, p); return loadMe(); };
  const logout = async () => { setTokens(null); setMe(null); await clearAll().catch(() => {}); };

  const value = {
    me, ready, gym: me?.gym || gym, user: me?.user, member: me?.member, login, logout, reload: loadMe,
    isTrainer: !!me?.user?.is_trainer, isStudent: !!me?.member,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
