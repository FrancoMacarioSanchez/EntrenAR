import { lazy, Suspense, useCallback, useState } from "react";
import Icon from "../components/Icon";
import { ErrorBoundary, Loader, Segmented } from "../components/ui";
import { normalizeAvatar, SCULPT_REGIONS, SKIN_TONES } from "./avatarSpec";

const BodyViewer = lazy(() => import("./BodyViewer"));

function Slider({ label, left, right, value, onChange }) {
  return (
    <div className="slider">
      <div className="row between"><b>{label}</b><small className="muted">{Math.round(value * 100)}%</small></div>
      <input type="range" min="0" max="1" step="0.05" value={value} onChange={(e) => onChange(+e.target.value)} />
      <div className="row between"><small className="muted">{left}</small><small className="muted">{right}</small></div>
    </div>
  );
}

/** Editor del avatar: vista previa en 3D, forma del cuerpo y moldeado (sin ropa ni pelo). */
export default function AvatarEditor({ avatar, sex, measures, onSave, onCancel, saving }) {
  const [a, setA] = useState(() => normalizeAvatar(avatar, sex));
  const [tab, setTab] = useState("cuerpo");
  const set = (patch) => setA((x) => normalizeAvatar({ ...x, ...patch }));
  const [region, setRegion] = useState(null);
  const sculpting = tab === "moldear";
  const setSculpt = useCallback((r, v) => setA((x) => normalizeAvatar({ ...x, sculpt: { ...x.sculpt, [r]: v } })), []);
  // «Sorprendeme»: solo forma del cuerpo (la app no personaliza ropa ni pelo)
  const randomBody = () => set({
    muscle: Math.round(Math.random() * 10) / 10, fat: Math.round(Math.random() * 8) / 10,
    sculpt: Object.fromEntries(SCULPT_REGIONS.filter(() => Math.random() < 0.3).map(([k]) => [k, Math.round((Math.random() - 0.5) * 8) / 10])),
  });

  return (
    <div className="avatar-editor">
      <div className="ae-preview">
        <ErrorBoundary fallback={<p className="muted center">Tu dispositivo no puede mostrar el 3D, pero el avatar se guarda igual.</p>}>
          <Suspense fallback={<Loader text="Cargando avatar…" />}>
            <BodyViewer avatar={a} measures={measures} interactive={false} height={sculpting ? 380 : 300}
              sculpt={sculpting} onSculpt={setSculpt} onSculptRegion={setRegion} />
          </Suspense>
        </ErrorBoundary>
        {!sculpting && <button type="button" className="btn sm ae-random" onClick={randomBody}>🎲 Sorprendeme</button>}
        {sculpting && <p className="ae-hint">Tocá una parte del cuerpo y arrastrá <b>hacia afuera</b> para agrandarla o <b>hacia adentro</b> para achicarla. Girá el avatar arrastrando fuera del cuerpo.</p>}
      </div>
      <Segmented value={tab} onChange={setTab} options={[["cuerpo", "Cuerpo"], ["moldear", "Moldear"]]} />
      <div className="ae-body">
        {tab === "cuerpo" && <div className="stack">
          <div><b className="ae-label">Sexo</b><Segmented value={a.sex} onChange={(v) => set({ sex: v })} options={[["M", "Hombre"], ["F", "Mujer"]]} /></div>
          <div><b className="ae-label">Tono de piel</b>
            <div className="swatches">{SKIN_TONES.map((c, i) => <button key={c} type="button" className={`sw lg ${a.skin === i ? "on" : ""}`} style={{ background: c }} onClick={() => set({ skin: i })} />)}</div></div>
          <Slider label="Musculatura" left="Liviana" right="Muy marcada" value={a.muscle} onChange={(v) => set({ muscle: v })} />
          <Slider label="Grasa corporal" left="Baja" right="Alta" value={a.fat} onChange={(v) => set({ fat: v })} />
          <label className="row toggle-row"><input type="checkbox" checked={a.use_measures} onChange={(e) => set({ use_measures: e.target.checked })} />
            <span><b>Que el avatar refleje mis medidas</b><br /><small className="muted">Cintura, cadera, brazos y piernas cambian según lo que cargues.</small></span></label>
        </div>}
        {sculpting && <div className="stack">
          {SCULPT_REGIONS.map(([k, label]) => (
            <div key={k} className={`sculpt-row ${region === k ? "on" : ""}`}>
              <span>{label}</span>
              <input type="range" min="-1" max="1" step="0.05" value={a.sculpt[k] || 0} aria-label={label}
                onChange={(e) => { setRegion(k); setSculpt(k, +e.target.value); }} />
              <small className="muted">{a.sculpt[k] ? `${a.sculpt[k] > 0 ? "+" : ""}${Math.round(a.sculpt[k] * 40)}%` : "—"}</small>
            </div>
          ))}
          <button type="button" className="btn sm" disabled={!Object.keys(a.sculpt).length} onClick={() => set({ sculpt: {} })}>Volver a la forma original</button>
          <small className="muted">El moldeado se suma a tus medidas reales cuando «reflejar mis medidas» está activado.</small>
        </div>}
      </div>
      <div className="row ae-actions">
        {onCancel && <button type="button" className="btn block" onClick={onCancel}>Cancelar</button>}
        <button type="button" className="btn primary block" disabled={saving} onClick={() => onSave(a)}>{saving ? "Guardando…" : "Guardar avatar"}</button>
      </div>
    </div>
  );
}
