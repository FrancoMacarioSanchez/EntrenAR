import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "../../../components/Icon";
import { useToast } from "../../../components/Toast";
import { Sheet } from "../../../components/ui";
import { api, del, get, post } from "../../../lib/api";
import { num } from "../../../lib/format";
import { MEAL_LABEL, compressImage, createDictation, itemFromFood, itemsFromAI } from "../../../lib/nutrition";
import { BarcodeScanner, FoodSearch, LabelForm, lookupBarcode } from "./parts";

const TO = { desayuno: "al desayuno", almuerzo: "al almuerzo", merienda: "a la merienda", cena: "a la cena", colacion: "a la colación" };
const prevDay = (d) => { const x = new Date(d + "T12:00:00"); x.setDate(x.getDate() - 1); return x.toISOString().slice(0, 10); };

// Elegir cómo cargar la comida: foto, texto/voz, código, búsqueda, habituales o copiar de ayer.
export default function AddFoodSheet({ open, onClose, mealType, date, ai, onDraft, onLogged }) {
  const toast = useToast();
  const [mode, setMode] = useState(null);
  const [busy, setBusy] = useState("");
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [cart, setCart] = useState([]);
  const [recent, setRecent] = useState([]);
  const [saved, setSaved] = useState(null);
  const [missingCode, setMissingCode] = useState(null);
  const fileRef = useRef(null);
  const recRef = useRef(null);

  useEffect(() => {
    if (!open) { setMode(null); setText(""); setCart([]); setBusy(""); setMissingCode(null); recRef.current?.stop(); }
  }, [open]);
  useEffect(() => {
    if (mode === "search" && !recent.length) get("/me/nutrition/recent/").then(setRecent).catch(() => {});
    if (mode === "saved" && saved === null) get("/me/nutrition/saved/").then(setSaved).catch(() => setSaved([]));
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const aiLeft = ai ? Math.max(0, ai.limit - ai.used) : 0;
  const aiReason = !ai ? "not_enabled" : ai.reason ?? (ai.limit <= 0 ? "not_enabled" : !ai.configured ? "not_configured" : aiLeft <= 0 ? "limit" : null);
  const AI_MSG = {
    not_enabled: ["El análisis con IA no está activado", "Tu gimnasio no lo tiene activado para vos. Podés cargar la comida buscando los alimentos, con el código de barras o con tus habituales."],
    budget: ["El análisis con IA está pausado por este mes", "Tu gimnasio llegó al consumo máximo del mes. Mientras tanto, cargá la comida buscando los alimentos o con tus habituales."],
    not_configured: ["El análisis con IA todavía no está activado", "Tu gimnasio todavía no lo habilitó. Mientras tanto, cargá la comida buscando los alimentos."],
    limit: [`Ya usaste los ${ai?.limit ?? 0} análisis de hoy`, "Mañana se renuevan. Mientras tanto podés buscar los alimentos o usar tus habituales."],
  };
  // Los botones de IA nunca quedan muertos: si no se puede, explican por qué.
  const withAI = (fn) => () => (aiReason ? setMode("ai_blocked") : fn());
  const label = MEAL_LABEL[mealType];

  const analyze = async (form, source) => {
    setBusy(source === "photo" ? "Analizando tu plato…" : "Interpretando lo que comiste…");
    try {
      const r = await api("/me/nutrition/analyze/", { method: "POST", form });
      onDraft({ items: itemsFromAI(r.items), ai_request: r.ai_request, meal_name: r.meal_name, notes: r.notes,
        image: r.image, source, demo: r.demo });
    } catch (e) {
      if (e.data?.reason) setMode("ai_blocked"); else toast(e.message, "bad", 6000);
    } finally { setBusy(""); }
  };

  const onPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const { blob } = await compressImage(file);
    const fd = new FormData();
    fd.append("photo", blob, "comida.jpg");
    analyze(fd, "photo");
  };

  const onText = () => {
    recRef.current?.stop();
    const fd = new FormData();
    fd.append("text", text.trim());
    analyze(fd, "text");
  };

  const toggleMic = () => {
    if (listening) { recRef.current?.stop(); return; }
    const base = text ? text.trim() + " " : "";
    const rec = createDictation({ onText: (t) => setText(base + t), onEnd: () => setListening(false) });
    if (!rec) { toast("Tu navegador no permite dictar. Usá el micrófono del teclado.", "info"); return; }
    recRef.current = rec; rec.start(); setListening(true);
  };

  const onCode = useCallback(async (code) => {
    setBusy("Buscando el producto…");
    try {
      const food = await lookupBarcode(code);
      onDraft({ items: [itemFromFood(food, food.portions?.[0]?.grams ?? 100)], source: "barcode" });
    } catch (e) {
      if (e.status === 404) setMissingCode(code); else toast(e.message, "bad");
    } finally { setBusy(""); }
  }, [onDraft, toast]);

  const logSaved = async (s) => {
    setBusy("Cargando…");
    try { await post(`/me/nutrition/saved/${s.id}/`, { meal_type: mealType, date }); toast(`${s.name} cargado`, "ok"); onLogged(); }
    catch (e) { toast(e.message, "bad"); } finally { setBusy(""); }
  };

  const removeSaved = async (s) => {
    if (!confirm(`¿Borrar «${s.name}» de tus habituales?`)) return;
    await del(`/me/nutrition/saved/${s.id}/`).catch(() => {});
    setSaved((l) => l.filter((x) => x.id !== s.id));
  };

  const copyYesterday = async () => {
    setBusy("Copiando…");
    try {
      await post("/me/nutrition/copy/", { from_date: prevDay(date), to_date: date, meal_type: mealType });
      toast(`${label} de ayer copiado`, "ok"); onLogged();
    } catch (e) { toast(e.message, "bad"); } finally { setBusy(""); }
  };

  const titles = { ai_blocked: "Análisis con IA", photo: "Foto del plato", text: "Escribí o dictá", barcode: "Código de barras", search: "Buscar alimentos", saved: "Comidas habituales" };

  return (
    <Sheet open={open} onClose={onClose} title={mode ? titles[mode] : `Agregar ${TO[mealType] || ""}`} tall={mode === "search" || mode === "barcode"}>
      <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={onPhoto} />
      {busy ? (
        <div className="ai-busy"><span className="ai-orb"><Icon name="sparkle" size={30} /></span><b>{busy}</b>
          <small className="muted">Tarda unos segundos.</small></div>
      ) : !mode ? (
        <div className="stack">
          <div className="add-grid">
            <button className={`add-opt hero ${aiReason ? "locked" : ""}`} onClick={withAI(() => fileRef.current.click())}>
              <Icon name="camera" size={26} /><b>Sacale una foto</b><small>La IA reconoce el plato y las porciones</small></button>
            <button className={`add-opt ${aiReason ? "locked" : ""}`} onClick={withAI(() => setMode("text"))}>
              <Icon name="mic" size={22} /><b>Escribí o dictá</b><small>«2 huevos revueltos y una tostada»</small></button>
            <button className="add-opt" onClick={() => setMode("barcode")}>
              <Icon name="barcode" size={22} /><b>Código de barras</b><small>Productos envasados</small></button>
            <button className="add-opt" onClick={() => setMode("search")}>
              <Icon name="search" size={22} /><b>Buscar</b><small>En la base de alimentos</small></button>
            <button className="add-opt" onClick={() => setMode("saved")}>
              <Icon name="bookmark" size={22} /><b>Habituales</b><small>Tus comidas guardadas</small></button>
            <button className="add-opt" onClick={copyYesterday}>
              <Icon name="repeat" size={22} /><b>Copiar de ayer</b><small>{label} de ayer, igual</small></button>
          </div>
          <small className="muted center block">{aiReason ? `${AI_MSG[aiReason][0]}.` : `Análisis con IA: te quedan ${aiLeft} de ${ai.limit} por hoy.`}</small>
        </div>
      ) : mode === "ai_blocked" ? (
        <div className="stack center ai-blocked">
          <span className="ai-orb off"><Icon name="sparkle" size={30} /></span>
          <b>{AI_MSG[aiReason]?.[0]}</b>
          <p className="muted">{AI_MSG[aiReason]?.[1]}</p>
          <button className="btn primary block" onClick={() => setMode("search")}><Icon name="search" size={18} />Buscar alimentos</button>
          <button className="btn block" onClick={() => setMode("barcode")}><Icon name="barcode" size={18} />Escanear un código</button>
          <button className="btn ghost block" onClick={() => setMode(null)}>Volver</button>
        </div>
      ) : mode === "text" ? (
        <div className="stack">
          <div className="dictate">
            <textarea className="input" rows={4} maxLength={500} autoFocus value={text} onChange={(e) => setText(e.target.value)}
              placeholder="Ej: un plato de fideos con tuco, una milanesa al horno y una manzana" />
            <button type="button" className={`mic ${listening ? "on" : ""}`} onClick={toggleMic} aria-label="Dictar"><Icon name="mic" size={22} /></button>
          </div>
          {listening && <small className="c-brand">Escuchando… hablá normalmente.</small>}
          <small className="muted">Cuanto más detalle (cantidades, cómo estaba cocinado), mejor el cálculo.</small>
          <div className="row"><button className="btn" onClick={() => setMode(null)}>Volver</button>
            <button className="btn primary" style={{ flex: 1 }} disabled={text.trim().length < 3} onClick={onText}><Icon name="sparkle" size={18} />Calcular</button></div>
        </div>
      ) : mode === "barcode" ? (
        missingCode ? <LabelForm barcode={missingCode} onCancel={() => setMissingCode(null)}
          onCreated={(food) => onDraft({ items: [itemFromFood(food)], source: "barcode" })} />
          : <BarcodeScanner onCode={onCode} />
      ) : mode === "search" ? (
        <div className="stack">
          <FoodSearch recent={recent} onPick={(f) => { setCart((c) => [...c, itemFromFood(f)]); toast(`${f.name} agregado`, "ok", 1500); }} />
          {cart.length > 0 && (
            <button className="btn primary block sticky-bottom" onClick={() => onDraft({ items: cart, source: "manual" })}>
              Revisar {cart.length} {cart.length === 1 ? "alimento" : "alimentos"}<Icon name="next" size={18} /></button>
          )}
        </div>
      ) : mode === "saved" ? (
        <div className="stack">
          {saved === null ? <span className="spinner" /> : !saved.length ? (
            <p className="muted center">Todavía no guardaste comidas habituales. Al confirmar una comida, marcá «Guardar como habitual» y la próxima vez la cargás con un toque.</p>
          ) : saved.map((s) => (
            <div key={s.id} className="saved-row">
              <button onClick={() => logSaved(s)}><b>{s.name}</b><br />
                <small className="muted">{s.items.map((i) => i.name).join(", ")}</small><br />
                <small><b>{num(s.totals.kcal, 0)} kcal</b> · P {num(s.totals.protein, 0)} g</small></button>
              <button className="icon-btn" onClick={() => removeSaved(s)} aria-label="Borrar"><Icon name="trash" size={18} /></button>
            </div>
          ))}
        </div>
      ) : null}
    </Sheet>
  );
}
