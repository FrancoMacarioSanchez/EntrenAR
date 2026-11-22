import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { buildSpec } from "./avatarSpec";
import { AvatarEngine, regionOfZone } from "./morph/AvatarEngine";
import { ZONES, zoneFilled } from "./zones";

// Modelo del cuerpo: por defecto el adaptado de tools/avatar (VITE_AVATAR_GLB=none usa el generado por código)
const EXTERNAL_GLB = (import.meta.env.VITE_AVATAR_GLB ?? `${import.meta.env.BASE_URL}models/avatar_body.glb`).replace(/^none$/, "");

function shadowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const x = c.getContext("2d");
  const gr = x.createRadialGradient(64, 64, 4, 64, 64, 64);
  gr.addColorStop(0, "rgba(0,0,0,.35)");
  gr.addColorStop(1, "rgba(0,0,0,0)");
  x.fillStyle = gr;
  x.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

function webglOk() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch { return false; }
}

/**
 * Avatar 3D personalizable.
 * - avatar: configuración (piel, pelo, ropa, contextura…)  - measures: medidas para deformarlo
 * - interactive: muestra anillos tocables de cada zona (carga de medidas)
 * - sculpt: modo moldear (como en los Sims): se toca una zona y se arrastra hacia afuera/adentro
 *   → onSculpt(region, valor −1…1)
 */
export default function BodyViewer({ avatar, measures, values = {}, selected, onSelect, height = 460, interactive = true,
  sex, sculpt = false, onSculpt, onSculptRegion }) {
  const mount = useRef(null);
  const api = useRef({});
  const [fallback] = useState(() => !webglOk());
  const brand = getComputedStyle(document.documentElement).getPropertyValue("--brand").trim() || "#ff5a1f";

  const spec = useMemo(() => buildSpec(avatar || { sex }, measures || values),
    [avatar, measures, values, sex]);

  // escena (una sola vez)
  useEffect(() => {
    if (fallback) return;
    const el = mount.current;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, el.clientWidth / height, 0.05, 20);
    camera.position.set(0.9, 1.3, 3.3);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0.95, 0);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.minDistance = 0.6;
    controls.maxDistance = 5;
    controls.minPolarAngle = 0.3;
    controls.maxPolarAngle = 1.8;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 1.1;

    scene.add(new THREE.HemisphereLight(0xffffff, 0x3a4152, 1.25));
    const key = new THREE.DirectionalLight(0xfff4ea, 2.3);
    key.position.set(2, 3.2, 2.6);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xdfe8ff, 0.7);
    fill.position.set(-2.4, 1.6, 2);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(new THREE.Color(brand), 1.7);
    rim.position.set(-2.2, 2.2, -2.4);
    scene.add(rim);

    const floor = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5), new THREE.MeshBasicMaterial({
      map: shadowTexture(), transparent: true, depthWrite: false }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = 0.002;
    scene.add(floor);

    const root = new THREE.Group();
    scene.add(root);
    const rings = new THREE.Group();
    root.add(rings);
    const engine = new AvatarEngine(root, { externalUrl: EXTERNAL_GLB });
    api.current.engine = engine;

    // interacción
    const ray = new THREE.Raycaster();
    const ptr = new THREE.Vector2();
    const el2 = renderer.domElement;
    const pick = (e, objs) => {
      const r = el2.getBoundingClientRect();
      ptr.x = ((e.clientX - r.left) / r.width) * 2 - 1;
      ptr.y = -((e.clientY - r.top) / r.height) * 2 + 1;
      ray.setFromCamera(ptr, camera);
      return ray.intersectObjects(objs, false)[0];
    };
    const toScreen = (v) => {
      const p = v.clone().project(camera), r = el2.getBoundingClientRect();
      return [(p.x + 1) / 2 * r.width, (1 - p.y) / 2 * r.height];
    };
    let down = null, drag = null;

    // moldear: se registra en captura para ganarle a OrbitControls
    const onDownSculpt = (e) => {
      if (!api.current.sculpt) return;
      const hit = pick(e, engine.pickTargets);
      const region = hit && regionOfZone(engine.zoneFromHit(hit));
      if (!region) return;
      e.stopImmediatePropagation();
      controls.enabled = false;
      controls.autoRotate = false;
      const [hx] = toScreen(hit.point), [cx] = toScreen(new THREE.Vector3(0, hit.point.y, 0));
      const start = +(api.current.avatar?.sculpt?.[region] || 0);
      drag = { region, x: e.clientX, y: e.clientY, start, side: Math.abs(hx - cx) < 10 ? 0 : Math.sign(hx - cx),
        baseW: (engine.target[`girth_${region}`] || 0) - start, value: start };
      el2.setPointerCapture?.(e.pointerId);
      engine.setHighlight(region);
      api.current.onSculptRegion?.(region);
    };
    const onMove = (e) => {
      if (drag) {
        // hacia afuera (o hacia arriba en el centro del cuerpo) agranda; hacia adentro achica
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        const d = drag.side ? dx * drag.side - dy * 0.25 : -dy;
        drag.value = Math.round(Math.min(1, Math.max(-1, drag.start + d / 140)) * 100) / 100;
        engine.setWeight(`girth_${drag.region}`, drag.baseW + drag.value);
        return;
      }
      if (api.current.sculpt && e.pointerType === "mouse" && !e.buttons) {
        const hit = pick(e, engine.pickTargets);
        engine.setHighlight(hit ? regionOfZone(engine.zoneFromHit(hit)) : null);
        el2.style.cursor = hit ? "ew-resize" : "";
      }
    };
    const onUpSculpt = () => {
      if (!drag) return;
      api.current.onSculpt?.(drag.region, drag.value);
      drag = null;
      controls.enabled = true;
    };
    const onLeave = () => { if (!drag && api.current.sculpt) engine.setHighlight(null); };
    el2.addEventListener("pointerdown", onDownSculpt, { capture: true });
    el2.addEventListener("pointermove", onMove);
    el2.addEventListener("pointerup", onUpSculpt);
    el2.addEventListener("pointercancel", onUpSculpt);
    el2.addEventListener("pointerleave", onLeave);

    // tocar una zona (carga de medidas)
    const onDown = (e) => { down = { x: e.clientX, y: e.clientY }; controls.autoRotate = false; };
    const onUp = (e) => {
      if (api.current.sculpt || !api.current.interactive || !down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) return;
      const hit = pick(e, [...engine.pickTargets, ...(api.current.targets || [])]);
      if (!hit) return;
      const zone = hit.object.userData.zone || engine.zoneFromHit(hit);
      if (zone) api.current.onSelect?.(zone);
    };
    el2.addEventListener("pointerdown", onDown);
    el2.addEventListener("pointerup", onUp);

    let tween = null;
    api.current.focus = (zoneId) => {
      const s = api.current.scale || 1;
      const z = zoneId && api.current.zones?.[zoneId];
      const target = z ? new THREE.Vector3(z.pos[0] * s * 0.6, z.pos[1] * s, 0) : new THREE.Vector3(0, 0.95 * s, 0);
      const dist = z ? (z.r > 0.12 ? 1.4 : 1.05) * s : 3.3 * s;
      const dir = z ? new THREE.Vector3(z.pos[0] * 2.2 + (z.pos[0] === 0 ? 0.25 : 0), 0.18, 1).normalize()
        : camera.position.clone().sub(controls.target).normalize();
      tween = { t0: performance.now(), from: camera.position.clone(), fromT: controls.target.clone(),
        to: target.clone().add(dir.multiplyScalar(dist)), toT: target };
      controls.autoRotate = !z;
    };

    let raf;
    const clock = new THREE.Clock();
    let last = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const t = clock.getElapsedTime();
      engine.tick(Math.min(0.1, t - last));
      last = t;
      if (tween) {
        const k = Math.min(1, (performance.now() - tween.t0) / 700);
        const e = 1 - Math.pow(1 - k, 3);
        camera.position.lerpVectors(tween.from, tween.to, e);
        controls.target.lerpVectors(tween.fromT, tween.toT, e);
        if (k >= 1) tween = null;
      }
      const rings = api.current.rings || {};
      for (const id in rings) {
        const { ring, mat, z } = rings[id];
        const sel = id === api.current.selected;
        const s = sel ? 1.06 + Math.sin(t * 5) * 0.03 : 1;
        ring.scale.set(s, (z.flat || 1) * s, sel ? 1.6 : 1);
        mat.opacity = sel ? 1 : (api.current.filled?.[id] ? 0.95 : 0.5);
      }
      controls.update();
      renderer.render(scene, camera);
    };
    loop();

    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      renderer.setSize(w, height);
      camera.aspect = w / height;
      camera.updateProjectionMatrix();
    });
    ro.observe(el);

    api.current.root = root;
    api.current.ringsGroup = rings;
    api.current.camera = camera;
    api.current.controls = controls;
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      el2.removeEventListener("pointerdown", onDownSculpt, { capture: true });
      el2.removeEventListener("pointermove", onMove);
      el2.removeEventListener("pointerup", onUpSculpt);
      el2.removeEventListener("pointercancel", onUpSculpt);
      el2.removeEventListener("pointerleave", onLeave);
      el2.removeEventListener("pointerdown", onDown);
      el2.removeEventListener("pointerup", onUp);
      controls.dispose();
      engine.dispose();
      scene.traverse((o) => { if (o.geometry && !o.userData.avatar) o.geometry.dispose(); });
      renderer.dispose();
      el.removeChild(renderer.domElement);
      api.current = {};
    };
  }, [height, fallback, brand]);

  // actualiza el avatar (pesos de morph en tiempo real; la malla solo se regenera si cambia el peinado)
  useEffect(() => {
    const engine = api.current.engine;
    const group = api.current.ringsGroup;
    if (!engine || !group) return;
    let cancelled = false;
    api.current.avatar = spec.avatar;
    api.current.scale = spec.scale;
    api.current.sculpt = sculpt;
    // anillos medidos sobre la superficie real del cuerpo actual
    api.current.refreshRings = () => {
      api.current.ringsAt = performance.now();
      const zones = engine.rings();
      api.current.zones = zones;
      for (const c of [...group.children]) { group.remove(c); c.traverse((o) => { o.geometry?.dispose(); o.material?.dispose?.(); }); }
      const rings = {}, targets = [];
      if (interactive && !api.current.sculpt) {
        for (const z of ZONES) {
          const zs = zones[z.id];
          if (!zs) continue;
          const grp = new THREE.Group();
          grp.position.set(...zs.pos);
          grp.rotation.z = zs.tilt || 0;
          const ringMat = new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.55, roughness: 0.3 });
          const ring = new THREE.Mesh(new THREE.TorusGeometry(zs.r, 0.0085, 10, 72), ringMat);
          ring.rotation.x = Math.PI / 2;
          ring.scale.y = zs.flat || 1;
          grp.add(ring);
          const hit = new THREE.Mesh(new THREE.CylinderGeometry(zs.r * 1.05, zs.r * 1.05, 0.07, 24, 1, true),
            new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
          hit.scale.z = zs.flat || 1;
          hit.userData.zone = z.id;
          grp.add(hit);
          targets.push(hit);
          group.add(grp);
          rings[z.id] = { ring, mat: ringMat, z: zs };
        }
      }
      api.current.rings = rings;
      api.current.targets = targets;
      api.current.colorize?.();
    };
    engine.update(spec.avatar, measures || values).then(() => {
      if (cancelled) return;
      api.current.refreshRings();
      if (!api.current.didFocus) {
        api.current.didFocus = true;
        api.current.controls?.target.set(0, 0.95 * spec.scale, 0);
        if (interactive && api.current.selected) api.current.focus?.(api.current.selected);
      }
    }).catch((e) => console.warn("No se pudo generar el avatar:", e));
    return () => { cancelled = true; };
  }, [spec, interactive, measures, values, sculpt]);

  // modo moldear
  useEffect(() => {
    api.current.sculpt = sculpt;
    api.current.onSculpt = onSculpt;
    api.current.onSculptRegion = onSculptRegion;
    const engine = api.current.engine;
    if (!engine) return;
    if (!sculpt) engine.setHighlight(null);
    if (api.current.controls) api.current.controls.autoRotate = !sculpt && !interactive;
  }, [sculpt, onSculpt, onSculptRegion, interactive]);

  // selección y colores de los anillos
  useEffect(() => {
    api.current.onSelect = onSelect;
    api.current.selected = selected;
    api.current.interactive = interactive;
    const filled = {};
    for (const z of ZONES) filled[z.id] = zoneFilled(z, values);
    api.current.filled = filled;
    api.current.colorize = () => {
      const rings = api.current.rings || {};
      for (const id in rings) {
        const c = id === api.current.selected ? brand : api.current.filled?.[id] ? "#22c55e" : "#ffffff";
        rings[id].mat.color.set(c);
        rings[id].mat.emissive.set(id === api.current.selected ? brand : api.current.filled?.[id] ? "#0a5c2a" : "#000000");
      }
    };
    api.current.colorize();
  }, [selected, values, onSelect, brand, interactive]);

  useEffect(() => { if (interactive) api.current.focus?.(selected); }, [selected, interactive]);

  if (fallback) {
    if (!interactive) return null;
    return (
      <div className="zone-grid">
        {ZONES.map((z) => (
          <button key={z.id} className={`zone-btn ${selected === z.id ? "on" : ""} ${zoneFilled(z, values) ? "ok" : ""}`}
            onClick={() => onSelect(z.id)}>{z.label}</button>
        ))}
      </div>
    );
  }
  return <div ref={mount} className="viewer3d" style={{ height }} />;
}
