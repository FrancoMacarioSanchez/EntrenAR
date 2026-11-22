import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// Backend Django (runserver) — la PWA se abre en http://demo.localhost:5173/app/
const BACKEND = process.env.BACKEND || "http://127.0.0.1:8082";

export default defineConfig({
  base: "/app/",
  plugins: [
    react(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.js",
      injectRegister: false,
      manifest: false, // el manifest lo arma Django con el nombre y colores de cada gimnasio
      injectManifest: { globPatterns: ["**/*.{js,css,html,svg,png,woff2}"] },
      devOptions: { enabled: true, type: "module" },
    }),
  ],
  server: {
    host: true,
    port: 5173,
    allowedHosts: [".localhost"],
    proxy: {
      "/api": { target: BACKEND, changeOrigin: false },
      "/media": { target: BACKEND, changeOrigin: false },
      "/app/manifest.webmanifest": { target: BACKEND, changeOrigin: false },
    },
  },
  worker: { format: "es" }, // el generador de avatares corre en un Web Worker con imports ES
  build: {
    outDir: "../backend/pwa_dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
    rollupOptions: { output: { manualChunks: { three: ["three"], react: ["react", "react-dom", "react-router-dom"] } } },
  },
});
