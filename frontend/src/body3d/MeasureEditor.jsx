import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "../components/Icon";
import { ErrorBoundary, Field, Loader, Segmented, Stepper } from "../components/ui";
import { compute, METHOD_LABELS, validate } from "../lib/body";
import { kv } from "../lib/db";
import { today } from "../lib/format";
import { SKINFOLD_FIELDS, ZONES, zoneFilled } from "./zones";

const BodyViewer = lazy(() => import("./BodyViewer"));

const GROUPS = [
  ["Tronco", ["neck", "shoulders", "chest", "waist", "abdomen", "hip"]],
  ["Brazos", ["arm_right", "arm_left", "forearm_right", "forearm_left", "wrist"]],
  ["Piernas", ["thigh_right", "thigh_left", "calf_right", "calf_left"]],
];
const LABELS = { weight_kg: "El peso", height_cm: "La altura", bioimpedance_bf: "El % de bioimpedancia" };
ZONES.forEach((z) => z.fields.forEach(([f, l]) => { LABELS[f] = `${z.label}${z.fields.length > 1 ? ` (${l.toLowerCase()})` : ""}`; }));
SKINFOLD_FIELDS.forEach(([f, l]) => { LABELS[f] = `Pliegue ${l.toLowerCase()}`; });

export function Results({ r, sex }) {
  if (!r || r.body_fat == null) {
    return <p className="muted">Cargá peso, altura, cuello y {sex === "F" ? "cintura y cadera" : "cintura o abdomen"} para estimar tu composición.</p>;
  }
  return (
    <div className="results">
      <div className="bf-hero">
        <div><small>Grasa corporal estimada</small><b>{r.body_fat}%</b><span className="pill">{r.classification}</span></div>
        <div className="bf-split">
          <div><small>Masa magra</small><b>{r.lean_mass ?? "—"} kg</b></div>
          <div><small>Masa grasa</small><b>{r.fat_mass ?? "—"} kg</b></div>
        </div>
      </div>
      <div className="grid3">
        <div className="mini"><small>IMC</small><b>{r.bmi ?? "—"}</b></div>
        <div className="mini"><small>FFMI</small><b>{r.ffmi ?? "—"}</b></div>
        <div className="mini"><small>Cintura/altura</small><b>{r.whtr ?? "—"}</b></div>
      </div>
      <details className="methods">
        <summary>Comparar métodos ({METHOD_LABELS[r.method] || r.method})</summary>
        {Object.entries(r.methods || {}).map(([k, v]) => (
          <div className="row between" key={k}><span>{METHOD_LABELS[k]}</span><b>{v == null ? "faltan datos" : `${v}%`}</b></div>
        ))}
        <small className="muted">Son estimaciones. La más precisa disponible se usa como principal (pliegues &gt; US Navy &gt; fórmulas por IMC).</small>
      </details>
    </div>
  );
}

/** Campo numérico compacto para la lista rápida. */
function NumField({ f, value, onChange, last, error, onFocus, unit = "cm" }) {
  return (
    <div className={`num-field ${error ? "has-error" : ""} ${value !== "" && value != null ? "filled" : ""}`}>
      <span className="nf-label">{LABELS[f]}{last != null && <small> · antes {last}</small>}</span>
      <div className="nf-input">
        <input inputMode="decimal" enterKeyHint="next" value={value ?? ""} placeholder={last != null ? String(last) : "—"}
          onChange={(e) => onChange(e.target.value.replace(",", "."))} onFocus={onFocus} />
        <span>{unit}</span>
      </div>
      {error && <small className="field-error">{error}</small>}
    </div>
  );
}

function ZoneGrid({ values, current, onPick }) {
  return (
    <div className="zone-grid">
      {ZONES.map((z, i) => (
        <button key={z.id} type="button" className={`zone-btn ${current === i ? "on" : ""} ${zoneFilled(z, values) ? "ok" : ""}`}
          onClick={() => onPick(i)}>{zoneFilled(z, values) && "✓ "}{z.label}</button>
      ))}
    </div>
  );
}

const EMPTY = { weight_kg: "", height_cm: "", bioimpedance_bf: "", notes: "" };
const nonEmpty = (o) => Object.fromEntries(Object.entries(o).filter(([, x]) => x !== "" && x != null));

export default function MeasureEditor({ member, last, onSave, saving, draftKey = "measure:draft", avatar, onEditAvatar }) {
  const [sex, setSex] = useState(member?.sex || "M");
  const [v, setV] = useState(() => ({ ...EMPTY, date: today(), height_cm: last?.height_cm ?? member?.height_cm ?? "" }));
  const [mode, setMode] = useState("guiado");
  const [idx, setIdx] = useState(0);
  const [skin, setSkin] = useState(false);
  const [errors, setErrors] = useState({});
  const [restored, setRestored] = useState(false);
  const loaded = useRef(false);
  const firstInput = useRef(null);

  // borrador: si se cierra la app a mitad de la carga, no se pierde nada
  useEffect(() => {
    kv.get(draftKey).then((d) => {
      if (d?.values && Object.entries(d.values).some(([k, x]) => k !== "date" && k !== "height_cm" && x !== "" && x != null)) {
        setV((cur) => ({ ...cur, ...d.values })); if (d.sex) setSex(d.sex); setRestored(true);
      }
    }).catch(() => {}).finally(() => { loaded.current = true; });
  }, [draftKey]);
  useEffect(() => {
    if (!loaded.current) return;
    const t = setTimeout(() => kv.set(draftKey, { values: v, sex }).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [v, sex, draftKey]);

  const set = (k, val) => {
    setV((x) => ({ ...x, [k]: val }));
    if (errors[k] || errors.__all__) setErrors((e) => { const n = { ...e }; delete n[k]; delete n.__all__; return n; });
  };
  const r = useMemo(() => compute(v, { sex, age: member?.age, height: member?.height_cm }), [v, sex, member]);
  const filled = ZONES.filter((z) => zoneFilled(z, v)).length;
  const zone = ZONES[idx];
  const onSelect = useCallback((id) => {
    const i = ZONES.findIndex((z) => z.id === id);
    if (i >= 0) { setIdx(i); setTimeout(() => firstInput.current?.focus({ preventScroll: true }), 50); }
  }, []);
  const go = (d) => setIdx((i) => (i + d + ZONES.length) % ZONES.length);
  const lastVal = (f) => (last?.[f] != null ? last[f] : null);

  const discard = async () => {
    await kv.del(draftKey).catch(() => {});
    setV({ ...EMPTY, date: today(), height_cm: last?.height_cm ?? member?.height_cm ?? "" });
    setErrors({}); setRestored(false); setIdx(0);
  };

  const save = async () => {
    const { clean, errors: errs } = validate(v, LABELS);
    if (!Object.keys(clean).length && !Object.keys(errs).length) errs.__all__ = "Cargá al menos una medida (por ejemplo el peso o la cintura).";
    if (v.date > today()) errs.date = "La fecha no puede ser futura.";
    setErrors(errs);
    if (Object.keys(errs).length) {
      const z = ZONES.findIndex((zz) => zz.fields.some(([f]) => errs[f]));
      if (z >= 0) setIdx(z);
      document.querySelector(".measure-errors")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const payload = { ...clean, sex, date: v.date };
    if (v.notes) payload.notes = v.notes;
    const res = await onSave(payload);
    if (res?.ok) { await kv.del(draftKey).catch(() => {}); return; }
    if (res?.errors) setErrors(Object.fromEntries(Object.entries(res.errors).map(([k, m]) => [k, String(m)])));
  };

  const errorList = Object.entries(errors);
  const viewerFallback = <ZoneGrid values={v} current={idx} onPick={setIdx} />;

  return (
    <div className="stack measure">
      {restored && <div className="card tip row between"><span><Icon name="info" size={18} /> Recuperamos la medición que estabas cargando.</span>
        <button className="btn sm ghost" onClick={discard}>Empezar de cero</button></div>}

      <div className="card">
        <h3 style={{ marginBottom: 12 }}>Datos básicos</h3>
        <div className="grid2">
          <Field label="Peso (kg)" error={errors.weight_kg} hint={lastVal("weight_kg") != null ? `Antes: ${lastVal("weight_kg")} kg` : null}>
            <Stepper value={v.weight_kg} onChange={(x) => set("weight_kg", x)} step={0.1} placeholder={lastVal("weight_kg") != null ? String(lastVal("weight_kg")) : "—"} />
          </Field>
          <Field label="Altura (cm)" error={errors.height_cm}>
            <Stepper value={v.height_cm} onChange={(x) => set("height_cm", x)} step={0.5} placeholder="170" />
          </Field>
        </div>
        <div className="row between wrap" style={{ marginTop: 12 }}>
          <Segmented options={[["M", "Hombre"], ["F", "Mujer"]]} value={sex} onChange={setSex} />
          <input type="date" className="input" value={v.date} max={today()} onChange={(e) => set("date", e.target.value)} style={{ width: "auto" }} />
        </div>
      </div>

      <Segmented value={mode} onChange={setMode} options={[["guiado", "Guiado con 3D"], ["lista", "Lista rápida"]]} />

      {mode === "guiado" ? (
        <div className="card viewer-card">
          <div className="row between">
            <small className="muted">Tocá el cuerpo o usá las flechas · {filled}/{ZONES.length} zonas</small>
            <div className="row">
              <div className="progress-mini"><span style={{ width: `${(filled / ZONES.length) * 100}%` }} /></div>
              {onEditAvatar && <button type="button" className="btn sm" onClick={onEditAvatar}>🎨 Avatar</button>}
            </div>
          </div>
          <ErrorBoundary fallback={viewerFallback}>
            <Suspense fallback={<Loader text="Cargando modelo 3D…" />}>
              <BodyViewer avatar={{ ...(avatar || member?.avatar || {}), sex }} values={{ ...(last || {}), ...nonEmpty(v) }}
                selected={zone.id} onSelect={onSelect} height={360} />
            </Suspense>
          </ErrorBoundary>

          <div className="zone-panel">
            <div className="row between">
              <button type="button" className="icon-btn" onClick={() => go(-1)} aria-label="Zona anterior"><Icon name="back" /></button>
              <div className="center"><small className="muted">Zona {idx + 1} de {ZONES.length}</small><h3>{zone.label}</h3></div>
              <button type="button" className="icon-btn" onClick={() => go(1)} aria-label="Zona siguiente"><Icon name="next" /></button>
            </div>
            {zone.tip && <p className="zone-tip"><Icon name="info" size={15} /> {zone.tip}</p>}
            <div className={zone.fields.length > 1 ? "grid2" : ""}>
              {zone.fields.map(([f, l], i) => (
                <Field key={f} label={`${l} (cm)`} error={errors[f]} hint={lastVal(f) != null ? `Antes: ${lastVal(f)} cm` : null}>
                  <div className="big-input">
                    <input ref={i === 0 ? firstInput : null} inputMode="decimal" enterKeyHint="next" value={v[f] ?? ""}
                      placeholder={lastVal(f) != null ? String(lastVal(f)) : "0"}
                      onChange={(e) => set(f, e.target.value.replace(",", "."))}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); go(1); } }} />
                    <span>cm</span>
                  </div>
                </Field>
              ))}
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <button type="button" className="btn block" onClick={() => { zone.fields.forEach(([f]) => set(f, "")); go(1); }}>Saltar</button>
              <button type="button" className="btn primary block" onClick={() => go(1)}>Siguiente<Icon name="next" size={18} /></button>
            </div>
          </div>
          <div className="chips-scroll">
            {ZONES.map((x, i) => (
              <button key={x.id} type="button" className={`chip ${idx === i ? "on" : ""} ${zoneFilled(x, v) ? "ok" : ""}`} onClick={() => setIdx(i)}>
                {zoneFilled(x, v) && <Icon name="check" size={14} />}{x.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="card">
          {GROUPS.map(([title, fields]) => (
            <div key={title} className="nf-group">
              <h4>{title}</h4>
              <div className="nf-grid">
                {fields.flatMap((zid) => ZONES.find((z) => z.id === zid).fields.map(([f]) => f)).map((f) => (
                  <NumField key={f} f={f} value={v[f]} onChange={(x) => set(f, x)} last={lastVal(f)} error={errors[f]} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <button type="button" className="row between full-btn" onClick={() => setSkin(!skin)}>
          <span><b>Pliegues y bioimpedancia</b> <small className="muted">(opcional)</small></span><Icon name={skin ? "up" : "down"} />
        </button>
        {skin && <div className="nf-grid" style={{ marginTop: 12 }}>
          {SKINFOLD_FIELDS.map(([f]) => (
            <NumField key={f} f={f} unit="mm" value={v[f]} onChange={(x) => set(f, x)} last={lastVal(f)} error={errors[f]} />
          ))}
          <NumField f="bioimpedance_bf" unit="%" value={v.bioimpedance_bf} onChange={(x) => set("bioimpedance_bf", x)} error={errors.bioimpedance_bf} />
        </div>}
      </div>

      <div className="card"><h3 style={{ marginBottom: 10 }}>Tu composición</h3><Results r={r} sex={sex} /></div>

      <div className="card">
        <Field label="Notas (opcional)"><textarea className="input" value={v.notes} onChange={(e) => set("notes", e.target.value)}
          placeholder="Ej: medido en ayunas, después de entrenar…" /></Field>
      </div>

      {errorList.length > 0 && <div className="alert bad measure-errors">
        <b>Revisá estos datos:</b>
        <ul>{errorList.map(([k, m]) => <li key={k}>{k === "__all__" || k === "date" ? m : `${LABELS[k] || k}: ${m.replace(/^.*?: /, "")}`}</li>)}</ul>
      </div>}

      <button type="button" className="btn primary lg block sticky-save" disabled={saving} onClick={save}>
        {saving ? "Guardando…" : `Guardar medición${filled ? ` (${filled} zonas)` : ""}`}</button>
      <small className="muted center">Para comparar bien, medite siempre a la misma hora y en las mismas condiciones.</small>
    </div>
  );
}

