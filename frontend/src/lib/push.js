import { api } from "./api";

function urlB64ToUint8Array(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export async function enablePush(vapidKey) {
  if (!pushSupported()) throw new Error("Tu navegador no soporta notificaciones. En iPhone instalá la app en la pantalla de inicio primero.");
  if (!vapidKey) throw new Error("El gimnasio todavía no activó las notificaciones.");
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("No diste permiso para notificaciones.");
  const reg = await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToUint8Array(vapidKey) }));
  await api("/push/subscribe/", { method: "POST", body: sub.toJSON() });
  return true;
}

export async function pushEnabled() {
  if (!pushSupported() || Notification.permission !== "granted") return false;
  const reg = await navigator.serviceWorker.getRegistration("/app/");
  return !!(reg && (await reg.pushManager.getSubscription()));
}
