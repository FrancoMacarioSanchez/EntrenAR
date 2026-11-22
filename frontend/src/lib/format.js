export const money = (v) => "$ " + Number(v || 0).toLocaleString("es-AR", { maximumFractionDigits: 2 });
export const kg = (v) => (v == null ? "—" : `${Number(v).toLocaleString("es-AR", { maximumFractionDigits: 2 })} kg`);
export const num = (v, d = 1) => (v == null ? "—" : Number(v).toLocaleString("es-AR", { maximumFractionDigits: d }));
export function parseDate(d) { if (!d) return null; return typeof d === "string" && d.length === 10 ? new Date(d + "T12:00:00") : new Date(d); }
export const dateShort = (d) => (d ? parseDate(d).toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" }) : "—");
export const dateLong = (d) => (d ? parseDate(d).toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" }) : "—");
export const dayName = (d) => parseDate(d).toLocaleDateString("es-AR", { weekday: "short", day: "numeric" });
export function ago(d) {
  if (!d) return "nunca";
  const s = (Date.now() - parseDate(d).getTime()) / 1000;
  if (s < 60) return "recién";
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  const days = Math.floor(s / 86400);
  return days === 1 ? "ayer" : `hace ${days} días`;
}
export const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
export const today = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
export const greeting = () => { const h = new Date().getHours(); return h < 13 ? "Buen día" : h < 20 ? "Buenas tardes" : "Buenas noches"; };
