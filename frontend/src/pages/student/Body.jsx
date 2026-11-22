import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import AvatarEditor from "../../body3d/AvatarEditor";
import MeasureEditor, { Results } from "../../body3d/MeasureEditor";
import { ZONES } from "../../body3d/zones";
import { LineChart } from "../../components/Charts";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { Empty, ErrorBoundary, Loader, Segmented, Sheet } from "../../components/ui";
import { api, del, post, put } from "../../lib/api";
import { dateShort, num, today } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { enqueue, onSync, uuid } from "../../lib/sync";

const BodyViewer = lazy(() => import("../../body3d/BodyViewer"));

export default function Body() {
  const toast = useToast();
  const { data, loading, reload } = useApi("/me/measurements/");
  const photos = useApi("/me/photos/");
  const [tab, setTab] = useState("nueva");
  const [saving, setSaving] = useState(false);
  const [metric, setMetric] = useState("weight_kg");
  const file = useRef();
  const [pose, setPose] = useState("front");
  const [sp, setSp] = useSearchParams();
  const [avatar, setAvatar] = useState(null);
  const [editAvatar, setEditAvatar] = useState(sp.get("avatar") === "1");
  const [savingAvatar, setSavingAvatar] = useState(false);
  useEffect(() => { if (data?.member && avatar === null) setAvatar(data.member.avatar || {}); }, [data, avatar]);
  const saveAvatar = async (a) => {
    setSavingAvatar(true);
    try { const r = await put("/me/avatar/", a); setAvatar(r.avatar); setEditAvatar(false); setSp({}); toast("¡Avatar guardado!", "success"); }
    catch (e) { toast(e.message, "error"); } finally { setSavingAvatar(false); }
  };
  const list = data?.results || [];
  const last = list[0];

  // Con conexión se guarda directo (y se ven los errores reales); sin conexión queda en la cola.
  const save = async (payload) => {
    setSaving(true);
    const body = { ...payload, client_uuid: uuid() };
    try {
      await post("/me/measurements/", body);
      toast("¡Medición guardada!", "success");
      await reload();
      setTab("historial");
      return { ok: true };
    } catch (e) {
      if (e.status === 0) {
        await enqueue("measurement", body);
        toast("Sin conexión: quedó guardada en el teléfono y se envía sola cuando vuelva la señal.", "info", 6000);
        setTab("historial");
        return { ok: true };
      }
      toast(e.message || "No se pudo guardar la medición", "error", 6000);
      return { ok: false, errors: e.data?.errors };
    } finally { setSaving(false); }
  };

  // si una medición guardada sin conexión es rechazada al sincronizar, avisamos
  useEffect(() => onSync((ev) => {
    if (ev.type === "rejected") ev.results.filter((r) => r.type === "measurement")
      .forEach((r) => toast(`Una medición cargada sin conexión no se pudo guardar: ${r.error}`, "error", 8000));
    if (ev.type === "synced" && ev.results.some((r) => r.measurement)) reload();
  }), [toast, reload]);

  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const form = new FormData(); form.append("image", f); form.append("pose", pose); form.append("date", today());
    try { await api("/me/photos/", { method: "POST", form }); photos.reload(); toast("Foto guardada (solo la ven vos y tu entrenador)", "success"); }
    catch (err) { toast(err.message, "error"); }
  };

  if (loading && !data) return <Loader />;
  const pts = [...list].reverse().map((x) => ({ x: x.date, y: x[metric] }));
  return (
    <div className="page-pad stack">
      <h1 className="title">Mi cuerpo</h1>
      <Segmented value={tab} onChange={setTab} options={[["nueva", "Nueva medición"], ["historial", "Evolución"], ["fotos", "Fotos"]]} />
      {tab === "nueva" && <MeasureEditor member={data?.member} last={last} onSave={save} saving={saving}
        avatar={avatar} onEditAvatar={() => setEditAvatar(true)} />}
      {tab === "historial" && (list.length ? <>
        <div className="card avatar-card">
          <div className="row between"><div><h3>Tu avatar hoy</h3><small className="muted">Con tus medidas del {dateShort(last.date)}</small></div>
            <button className="btn sm" onClick={() => setEditAvatar(true)}>🎨 Personalizar</button></div>
          <ErrorBoundary fallback={null}><Suspense fallback={<Loader />}>
            <BodyViewer avatar={avatar || data.member.avatar} measures={last} interactive={false} height={320} />
          </Suspense></ErrorBoundary>
        </div>
        <div className="card">
          <Segmented value={metric} onChange={setMetric} options={[["weight_kg", "Peso"], ["body_fat", "% grasa"], ["lean_mass", "Magra"], ["waist", "Cintura"]]} />
          <LineChart points={pts} unit={metric === "body_fat" ? "%" : metric === "waist" ? " cm" : " kg"} yFormat={(v) => num(v, 1)} />
        </div>
        <div className="card"><h3 style={{ marginBottom: 10 }}>Última medición · {dateShort(last.date)}</h3><Results r={last.results} sex={data.member.sex} />
          {list[1] && <Diff a={last} b={list[1]} />}</div>
        <div className="card list">{list.map((x) => (
          <details key={x.id} className="li-details"><summary className="li"><span><b>{dateShort(x.date)}</b><br /><small className="muted">{x.weight_kg ?? "—"} kg · {x.body_fat ?? "—"}% grasa{x.recorded_by ? ` · ${x.recorded_by}` : ""}</small></span><Icon name="down" size={18} /></summary>
            <div className="grid3">{ZONES.flatMap((z) => z.fields).filter(([k]) => x[k] != null).map(([k, l]) => (
              <div className="mini" key={k}><small>{ZONES.find((z) => z.fields.some(([f]) => f === k)).label}{l.includes("Contra") ? " (c)" : ""}</small><b>{x[k]}</b></div>))}</div>
            <button className="btn sm ghost danger-text" onClick={async () => { if (confirm("¿Eliminar esta medición?")) { await del(`/me/measurements/${x.id}/`); reload(); } }}>
              <Icon name="trash" size={16} />Eliminar</button>
          </details>))}</div>
      </> : <Empty icon="body" title="Sin mediciones" action={<button className="btn primary" onClick={() => setTab("nueva")}>Cargar la primera</button>}>Medite cada 2 a 4 semanas, siempre en las mismas condiciones.</Empty>)}
      {tab === "fotos" && <div className="stack">
        <div className="card row between">
          <Segmented value={pose} onChange={setPose} options={[["front", "Frente"], ["side", "Perfil"], ["back", "Espalda"]]} />
          <button className="btn primary sm" onClick={() => file.current.click()}><Icon name="camera" size={16} />Subir</button>
          <input ref={file} type="file" accept="image/*" capture="environment" hidden onChange={upload} />
        </div>
        {photos.data?.results?.length ? <div className="photo-grid">{photos.data.results.map((p) => (
          <a key={p.id} href={p.image} target="_blank" rel="noreferrer"><img src={p.image} alt="" loading="lazy" /><small>{dateShort(p.date)} · {p.pose_label}</small></a>))}</div>
          : <Empty icon="camera" title="Sin fotos">Sacate fotos con la misma luz y pose para comparar tu progreso.</Empty>}
      </div>}
      <Sheet open={editAvatar} onClose={() => { setEditAvatar(false); setSp({}); }} title="Tu avatar" tall>
        {editAvatar && <AvatarEditor avatar={avatar || data?.member?.avatar} sex={data?.member?.sex} measures={last}
          saving={savingAvatar} onSave={saveAvatar} onCancel={() => { setEditAvatar(false); setSp({}); }} />}
      </Sheet>
    </div>
  );
}

function Diff({ a, b }) {
  const rows = [["weight_kg", "Peso", "kg"], ["body_fat", "% grasa", "%"], ["lean_mass", "Masa magra", "kg"], ["waist", "Cintura", "cm"], ["arm_right", "Brazo der.", "cm"]]
    .filter(([k]) => a[k] != null && b[k] != null);
  if (!rows.length) return null;
  return <div className="diff">{rows.map(([k, l, u]) => {
    const d = Math.round((a[k] - b[k]) * 10) / 10;
    return <div key={k} className="mini"><small>{l}</small><b className={d > 0 ? "up" : d < 0 ? "down" : ""}>{d > 0 ? "+" : ""}{d} {u}</b></div>;
  })}<small className="muted">vs. {dateShort(b.date)}</small></div>;
}
