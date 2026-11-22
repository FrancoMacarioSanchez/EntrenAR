import { useEffect, useRef, useState } from "react";
import Icon from "../../../components/Icon";
import { api, get } from "../../../lib/api";
import { num } from "../../../lib/format";
import { BARCODE_FORMATS, MACRO_COLORS, barcodeSupported } from "../../../lib/nutrition";

// Barras de macros: consumido / meta.
export function MacroBars({ totals, targets, compact }) {
  const rows = [["protein", "Proteínas"], ["carbs", "Carbohidratos"], ["fat", "Grasas"]];
  return (
    <div className={`macro-bars ${compact ? "compact" : ""}`}>
      {rows.map(([k, label]) => {
        const v = totals?.[k] || 0, t = targets?.[k];
        const pct = t ? Math.min(100, (v / t) * 100) : 0;
        return (
          <div key={k} className="macro-bar">
            <div className="row between"><span>{label}</span><b>{num(v, 0)}{t ? <small> / {t} g</small> : " g"}</b></div>
            <div className="track"><i style={{ width: `${t ? pct : 0}%`, background: MACRO_COLORS[k] }} className={t && v > t * 1.1 ? "over" : ""} /></div>
          </div>
        );
      })}
    </div>
  );
}

export function MacroLine({ m }) {
  return (
    <small className="macro-line">
      <b>{num(m.kcal, 0)} kcal</b>
      <span style={{ color: MACRO_COLORS.protein }}>P {num(m.protein, 0)}</span>
      <span style={{ color: MACRO_COLORS.carbs }}>C {num(m.carbs, 0)}</span>
      <span style={{ color: MACRO_COLORS.fat }}>G {num(m.fat, 0)}</span>
    </small>
  );
}

// Buscador del catálogo (con alimentos recientes cuando no hay texto).
export function FoodSearch({ onPick, autoFocus = true, recent = [] }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (q.trim().length < 2) { setRes(null); return; }
    const ctl = new AbortController();
    const t = setTimeout(async () => {
      setLoading(true);
      try { setRes(await api(`/foods/search/?q=${encodeURIComponent(q.trim())}`, { signal: ctl.signal })); }
      catch (e) { if (e.name !== "AbortError") setRes([]); }
      finally { setLoading(false); }
    }, 250);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [q]);
  const list = res ?? recent;
  return (
    <div className="food-search">
      <div className="search-box">
        <Icon name="search" size={18} />
        <input className="input" placeholder="Buscar: arroz, milanesa, yogur…" value={q} autoFocus={autoFocus}
          onChange={(e) => setQ(e.target.value)} />
        {loading && <span className="spinner sm" />}
      </div>
      {!res && recent.length > 0 && <small className="muted">Lo que más usás</small>}
      <div className="food-list">
        {list.map((f) => (
          <button key={f.id} className="food-row" onClick={() => onPick(f)}>
            <span><b>{f.name}</b>{!f.verified && <em className="pill xs">sin verificar</em>}<br />
              <small className="muted">{num(f.per100.kcal, 0)} kcal · P {num(f.per100.protein, 0)} · C {num(f.per100.carbs, 0)} · G {num(f.per100.fat, 0)} cada 100 {f.is_liquid ? "ml" : "g"}</small></span>
            <Icon name="plus" size={18} />
          </button>
        ))}
        {res && !res.length && <p className="muted center">No encontramos «{q}». Probá con otro nombre o cargalo con la etiqueta.</p>}
      </div>
    </div>
  );
}

// Escáner de código de barras: BarcodeDetector si existe, si no se escribe el número.
export function BarcodeScanner({ onCode }) {
  const video = useRef(null);
  const [state, setState] = useState(barcodeSupported() ? "starting" : "manual");
  const [code, setCode] = useState("");
  useEffect(() => {
    if (state === "manual") return undefined;
    let stream, raf, stopped = false;
    (async () => {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) { setState("manual"); return; }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      } catch { setState("manual"); return; }
      if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
      const v = video.current;
      v.srcObject = stream; v.setAttribute("playsinline", "true");
      await v.play().catch(() => {});
      setState("scanning");
      let detector;
      try { detector = new window.BarcodeDetector({ formats: BARCODE_FORMATS }); } catch { setState("manual"); return; }
      let busy = false;
      const loop = async () => {
        if (stopped) return;
        raf = requestAnimationFrame(loop);
        if (busy || v.readyState < 2) return;
        busy = true;
        try {
          const found = await detector.detect(v);
          if (found[0]?.rawValue) { stopped = true; navigator.vibrate?.(40); onCode(found[0].rawValue); }
        } catch { /* frame no listo */ } finally { busy = false; }
      };
      loop();
    })();
    return () => { stopped = true; cancelAnimationFrame(raf); stream?.getTracks().forEach((t) => t.stop()); };
  }, [state === "manual", onCode]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="stack">
      {state !== "manual" && (
        <div className="barcode-cam"><video ref={video} muted /><i className="barcode-line" />
          {state === "starting" && <span className="spinner" />}</div>
      )}
      <form className="row" onSubmit={(e) => { e.preventDefault(); if (code.trim()) onCode(code.trim()); }}>
        <input className="input" inputMode="numeric" placeholder="O escribí el número del código" value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
        <button className="btn primary" disabled={code.length < 8}>Buscar</button>
      </form>
      {state === "manual" && <small className="muted">Tu navegador no permite escanear con la cámara: escribí los números que están debajo de las barras.</small>}
    </div>
  );
}

// Carga desde la etiqueta cuando el producto no existe (queda sin verificar).
export function LabelForm({ barcode, onCreated, onCancel }) {
  const [f, setF] = useState({ name: "", brand: "", serving_g: "", kcal: "", protein: "", carbs: "", fat: "", fiber: "" });
  const [perServing, setPerServing] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value.replace(",", ".") });
  const submit = async (e) => {
    e.preventDefault(); setSaving(true); setErr("");
    const n = (v) => (v === "" ? null : Number(v));
    try {
      const food = await api("/foods/", { method: "POST", body: {
        name: f.name, brand: f.brand, barcode, serving_g: n(f.serving_g), per_serving: perServing && !!f.serving_g,
        per100: { kcal: n(f.kcal), protein: n(f.protein), carbs: n(f.carbs), fat: n(f.fat), fiber: n(f.fiber) } } });
      onCreated(food);
    } catch (e2) { setErr(e2.message); } finally { setSaving(false); }
  };
  return (
    <form className="stack" onSubmit={submit}>
      <p className="muted">No encontramos el producto. Cargalo con la tabla nutricional del envase y queda guardado para la próxima.</p>
      <input className="input" placeholder="Nombre del producto" value={f.name} onChange={set("name")} required />
      <input className="input" placeholder="Marca" value={f.brand} onChange={set("brand")} />
      <div className="seg"><button type="button" className={perServing ? "on" : ""} onClick={() => setPerServing(true)}>Valores por porción</button>
        <button type="button" className={!perServing ? "on" : ""} onClick={() => setPerServing(false)}>Por 100 g</button></div>
      <div className="grid2">
        <input className="input" inputMode="decimal" placeholder={perServing ? "Porción (g o ml)" : "Porción habitual (opcional)"} value={f.serving_g} onChange={set("serving_g")} required={perServing} />
        <input className="input" inputMode="decimal" placeholder="Calorías (kcal)" value={f.kcal} onChange={set("kcal")} required />
        <input className="input" inputMode="decimal" placeholder="Proteínas (g)" value={f.protein} onChange={set("protein")} />
        <input className="input" inputMode="decimal" placeholder="Carbohidratos (g)" value={f.carbs} onChange={set("carbs")} />
        <input className="input" inputMode="decimal" placeholder="Grasas totales (g)" value={f.fat} onChange={set("fat")} />
        <input className="input" inputMode="decimal" placeholder="Fibra (g)" value={f.fiber} onChange={set("fiber")} />
      </div>
      {err && <p className="danger-text">{err}</p>}
      <div className="row"><button type="button" className="btn" onClick={onCancel}>Cancelar</button>
        <button className="btn primary" style={{ flex: 1 }} disabled={saving}>{saving ? "Guardando…" : "Guardar producto"}</button></div>
    </form>
  );
}

export async function lookupBarcode(code) {
  return get(`/foods/barcode/${encodeURIComponent(code)}/`);
}
