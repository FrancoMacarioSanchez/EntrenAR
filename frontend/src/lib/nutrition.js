// Utilidades del módulo de nutrición.
export const MEALS = [
  ["desayuno", "Desayuno"], ["almuerzo", "Almuerzo"], ["merienda", "Merienda"], ["cena", "Cena"], ["colacion", "Colación"],
];
export const MEAL_LABEL = Object.fromEntries(MEALS);
export const MACRO_COLORS = { protein: "#3b82f6", carbs: "#f59e0b", fat: "#ec4899" };

export function guessMeal(date = new Date()) {
  const h = date.getHours();
  if (h < 11) return "desayuno";
  if (h < 15.5) return "almuerzo";
  if (h < 19.5) return "merienda";
  return "cena";
}

export const r1 = (v) => Math.round((Number(v) || 0) * 10) / 10;

export function scale(per100, grams) {
  const g = (Number(grams) || 0) / 100;
  return {
    kcal: r1(per100.kcal * g), protein: r1(per100.protein * g), carbs: r1(per100.carbs * g), fat: r1(per100.fat * g),
    fiber: per100.fiber == null ? null : r1(per100.fiber * g),
  };
}

export function sum(items, pick = (i) => i) {
  const t = { kcal: 0, protein: 0, carbs: 0, fat: 0 };
  for (const it of items) { const m = pick(it); for (const k in t) t[k] += Number(m?.[k]) || 0; }
  for (const k in t) t[k] = r1(t[k]);
  return t;
}

// Ítem del borrador a partir de un alimento del catálogo.
export function itemFromFood(food, grams) {
  const g = grams ?? food.last_grams ?? food.portions?.[0]?.grams ?? 100;
  return { key: crypto.randomUUID?.() || String(Math.random()), food_id: food.id, food, name: food.name, grams: g,
    portion: "", per100: food.per100, source: "catalogo" };
}

// Ítems de la IA → borrador editable.
export function itemsFromAI(items) {
  return items.map((it) => ({ ...it, key: crypto.randomUUID?.() || String(Math.random()), original_food_id: it.food_id }));
}

// Payload para el backend (los macros de catálogo se recalculan allá; solo se mandan per100 si no hay alimento).
export function toPayload(items) {
  return items.map((it) => ({
    food_id: it.food_id || null, name: it.name, grams: Number(it.grams), portion: it.portion || "",
    per100: it.food_id ? undefined : it.per100, from_ai: it.source === "ia",
    ai_term: it.ai_term, changed: !!it.ai_term && it.food_id && it.food_id !== it.original_food_id,
  }));
}

// Achica la foto en el teléfono antes de subirla (768 px alcanzan para reconocer comida y ahorran datos).
export async function compressImage(file, max = 768, quality = 0.82) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
    const s = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * s); c.height = Math.round(img.naturalHeight * s);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", quality));
    return { blob: blob || file, preview: c.toDataURL("image/jpeg", 0.7) };
  } catch {
    return { blob: file, preview: null };
  } finally { URL.revokeObjectURL(url); }
}

// Dictado por voz (Chrome / Android / Safari reciente). Devuelve null si el navegador no lo soporta.
export function createDictation({ onText, onEnd }) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.lang = "es-AR"; rec.interimResults = true; rec.continuous = false;
  rec.onresult = (e) => onText(Array.from(e.results).map((r) => r[0].transcript).join(" "));
  rec.onend = () => onEnd?.();
  rec.onerror = () => onEnd?.();
  return rec;
}

export const barcodeSupported = () => "BarcodeDetector" in window;
export const BARCODE_FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];
