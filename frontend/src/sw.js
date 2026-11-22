/* Service worker de EntrenAR: offline + notificaciones push. */
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from "workbox-strategies";
import { ExpirationPlugin } from "workbox-expiration";

self.skipWaiting();
self.addEventListener("activate", () => self.clients.claim());

cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST || []);

// Todas las rutas de la SPA devuelven index.html (funciona sin conexión)
try {
  registerRoute(new NavigationRoute(createHandlerBoundToURL("/app/index.html"), { allowlist: [/^\/app(\/|$)/] }));
} catch (e) { /* en desarrollo index.html no está precacheado */ }

// API: red primero, cache si no hay señal (solo GET)
registerRoute(({ url, request }) => url.pathname.startsWith("/api/") && request.method === "GET",
  new NetworkFirst({ cacheName: "api", networkTimeoutSeconds: 6,
    plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 7 * 24 * 3600 })] }));

// Imágenes subidas (fotos, ejercicios)
registerRoute(({ url }) => url.pathname.startsWith("/media/"),
  new CacheFirst({ cacheName: "media", plugins: [new ExpirationPlugin({ maxEntries: 300, maxAgeSeconds: 30 * 24 * 3600 })] }));

// Fuentes y modelos 3D
registerRoute(({ url }) => url.origin.includes("fonts.g") || url.pathname.endsWith(".glb"),
  new StaleWhileRevalidate({ cacheName: "assets" }));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: "EntrenAR", body: event.data?.text() }; }
  event.waitUntil(self.registration.showNotification(data.title || "EntrenAR", {
    body: data.body || "", icon: "/app/icons/icon-192.png", badge: "/app/icons/icon-192.png",
    data: { url: data.url || "/app/" }, vibrate: [80, 40, 80],
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/app/";
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) { if (c.url.includes("/app")) { c.focus(); c.navigate(url); return; } }
    return self.clients.openWindow(url);
  })());
});
