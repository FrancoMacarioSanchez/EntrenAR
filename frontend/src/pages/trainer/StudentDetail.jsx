import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import MeasureEditor, { Results } from "../../body3d/MeasureEditor";
import { Bars, LineChart } from "../../components/Charts";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { Avatar, Empty, Loader, Segmented, Sheet, Stat } from "../../components/ui";
import { api, post } from "../../lib/api";
import { ago, dateShort, num } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { uuid } from "../../lib/sync";
import { useAuth } from "../../state/auth";
import { HistoryView } from "../student/ExerciseHistory";
import { groupSets } from "../student/SessionDetail";

const STATE = { active: ["Al día", "ok"], expiring: ["Por vencer", "warn"], grace: ["Vencida (tolerancia)", "warn"],
  expired: ["Vencida", "bad"], frozen: ["Congelada", "info"], none: ["Sin plan", "bad"] };

export default function StudentDetail() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const { user, gym } = useAuth();
  const { data, loading, reload } = useApi(`/trainer/students/${id}/`);
  const [tab, setTab] = useState(sp.get("tab") || (sp.get("sesion") ? "sesiones" : "resumen"));
  const [exHist, setExHist] = useState(null);
  const [assign, setAssign] = useState(false);
  const [note, setNote] = useState({ text: "", visible_to_member: true });
  const [fb, setFb] = useState({});
  const [measuring, setMeasuring] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    const s = sp.get("sesion");
    if (s && data) document.getElementById(`s-${s}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [data, sp]);

  if (loading && !data) return <Loader />;
  if (!data) return null;
  const m = data.member, p = data.progress;
  const [stl, stk] = STATE[m.membership_state] || STATE.none;

  const openHistory = async (ex) => {
    setExHist({ loading: true, name: ex.name });
    try { setExHist(await api(`/trainer/students/${id}/exercises/${ex.id}/history/`)); } catch (e) { toast(e.message, "error"); setExHist(null); }
  };
  const sendNote = async () => {
    if (!note.text.trim()) return;
    await post(`/trainer/students/${id}/notes/`, note);
    setNote({ text: "", visible_to_member: true }); toast(note.visible_to_member ? "Mensaje enviado" : "Nota guardada", "success"); reload();
  };
  const sendFeedback = async (sid) => {
    await post(`/trainer/sessions/${sid}/feedback/`, { text: fb[sid] || "" });
    toast("Comentario enviado al alumno", "success"); reload();
  };
  const saveMeasure = async (payload) => {
    setSaving(true);
    try {
      await post(`/trainer/students/${id}/measurements/`, { ...payload, client_uuid: uuid() });
      toast("Medición guardada", "success"); setMeasuring(false); reload();
      return { ok: true };
    } catch (e) {
      toast(e.status === 0 ? "Sin conexión: probá de nuevo cuando vuelva la señal (la carga quedó guardada en el teléfono)." : e.message, "error", 6000);
      return { ok: false, errors: e.data?.errors };
    } finally { setSaving(false); }
  };

  return (
    <div className="page-pad stack">
      <div className="student-head">
        <Avatar src={m.photo} initials={m.initials} size={72} />
        <div>
          <h1 className="title">{m.name}</h1>
          <small className="muted">{m.age ? `${m.age} años · ` : ""}{m.goal_label}{m.height_cm ? ` · ${m.height_cm} cm` : ""}</small>
          <div className="row" style={{ gap: 6, marginTop: 6 }}>
            <span className={`pill ${stk}`}>{stl}</span>
            {!m.medical_ok && <span className="pill warn">Apto pendiente</span>}
            {m.trainer_id !== user.id && <button className="pill" onClick={async () => { await post(`/trainer/students/${id}/assign/`); toast("Ahora es tu alumno", "success"); reload(); }}>Asignarme</button>}
          </div>
        </div>
      </div>
      {m.medical_notes && <div className="card tip warn"><Icon name="info" size={18} /><span><b>Salud / lesiones:</b> {m.medical_notes}</span></div>}

      {gym?.nutrition !== false && <Link to={`/entrenador/nutricion/${id}`} className="card nutri-mini">
        <span className="ico-bubble"><Icon name="food" size={18} /></span>
        <span className="grow"><b>Nutrición</b><br /><small className="muted">Metas, adherencia y comidas registradas</small></span><Icon name="next" />
      </Link>}
      <Segmented value={tab} onChange={setTab} options={[["resumen", "Resumen"], ["rutinas", "Rutinas"], ["sesiones", "Entrenos"], ["medidas", "Medidas"], ["notas", "Notas"]]} />

      {tab === "resumen" && <>
        <div className="grid2">
          <div className="card"><Stat label="Entrenamientos" value={p.sessions_total} sub={`${p.sessions_month} este mes`} /></div>
          <div className="card"><Stat label="Racha" value={`${p.week_streak} sem.`} /></div>
          <div className="card"><Stat label="Récords" value={p.records.length} /></div>
          <div className="card"><Stat label="Ingresos 30 días" value={p.checkins_30d} /></div>
        </div>
        <div className="card"><div className="sec-head"><h3>Volumen semanal</h3></div>
          <Bars items={p.weeks.map((w) => ({ label: dateShort(w.week), value: w.volume }))} format={(v) => `${num(v, 0)} kg`} /></div>
        <section className="card"><div className="sec-head"><h3>Ejercicios</h3><small className="muted">tocá para ver la evolución</small></div>
          {p.exercises.length ? <div className="list">{p.exercises.map((e) => (
            <button key={e.id} className="li" onClick={() => openHistory(e)}><span style={{ textAlign: "left" }}><b>{e.name}</b><br /><small className="muted">{e.sets} series · {dateShort(e.last)}</small></span>
              <span className="row">{e.top_weight ? <b>{e.top_weight} kg</b> : null}<Icon name="chart" size={18} /></span></button>))}</div>
            : <p className="muted">Sin registros todavía.</p>}</section>
        {p.records.length > 0 && <section className="card"><div className="sec-head"><h3>🏆 Récords</h3></div>
          {p.records.slice(0, 10).map((r) => <div key={r.id} className="li"><span><b>{r.exercise_name}</b><br /><small className="muted">{ago(r.achieved_at)}</small></span><b className="c-brand">{r.label}</b></div>)}</section>}
      </>}

      {tab === "rutinas" && <>
        <div className="row"><Link className="btn primary block" to={`/entrenador/rutinas/nueva?member=${id}`}><Icon name="plus" size={18} />Nueva rutina</Link>
          <button className="btn block" onClick={() => setAssign(true)}><Icon name="copy" size={18} />Desde plantilla</button></div>
        {data.routines.length ? data.routines.map((r) => (
          <div key={r.id} className={`card ${r.is_active ? "active-border" : ""}`}>
            <div className="sec-head"><div><h3>{r.name} {r.is_active && <span className="pill ok xs">Activa</span>}</h3>
              <small className="muted">v{r.version} · desde {dateShort(r.start_date)} · {r.trainer || "—"}</small></div>
              <div className="row">{r.is_active && <Link className="btn sm" to={`/entrenador/rutinas/${r.id}`}><Icon name="edit" size={16} />Editar</Link>}</div></div>
            {r.days.map((d) => <details key={d.id} className="li-details"><summary className="li"><b>{d.name}</b><small className="muted">{d.exercises.length} ejercicios</small></summary>
              {d.exercises.map((e) => <div key={e.id} className="li"><small>{e.exercise.name}</small><small className="mono">{e.sets}×{e.reps_label}{e.target_weight ? ` · ${e.target_weight}kg` : ""}</small></div>)}</details>)}
          </div>)) : <Empty icon="list" title="Sin rutinas" />}
        <TemplatePicker open={assign} onClose={() => setAssign(false)} onPick={async (t) => {
          const r = await post(`/routines/${t.id}/duplicate/`, { member: id, name: t.name });
          setAssign(false); toast("Rutina asignada", "success"); nav(`/entrenador/rutinas/${r.id}`);
        }} />
      </>}

      {tab === "sesiones" && (data.sessions.length ? data.sessions.map((s) => (
        <div key={s.id} id={`s-${s.id}`} className={`card ${sp.get("sesion") === String(s.id) ? "active-border" : ""}`}>
          <div className="sec-head"><div><h3>{s.routine_day_name}</h3><small className="muted">{dateShort(s.date)} · {s.sets_count} series · {num(s.volume / 1000, 1)} t{s.duration_min ? ` · ${s.duration_min} min` : ""}</small></div>
            {s.feeling && <span style={{ fontSize: 24 }}>{["😫", "😕", "🙂", "💪", "🔥"][s.feeling - 1]}</span>}</div>
          {groupSets(s.sets).map((g) => <div key={g.name} className="li"><small><b>{g.name}</b></small>
            <small className="mono right">{g.sets.map((x) => `${x.weight != null ? x.weight + "×" : ""}${x.reps ?? ""}${x.duration_seconds ? x.duration_seconds + "s" : ""}${x.to_failure ? "F" : ""}`).join(" · ")}</small></div>)}
          {s.notes && <p className="note"><Icon name="msg" size={14} /> {s.notes}</p>}
          <div className="row" style={{ marginTop: 8 }}>
            <input className="input" placeholder={s.trainer_feedback || "Comentario para el alumno…"} value={fb[s.id] ?? ""} onChange={(e) => setFb({ ...fb, [s.id]: e.target.value })} />
            <button className="btn sm primary" onClick={() => sendFeedback(s.id)}><Icon name="msg" size={16} /></button></div>
          {s.trainer_feedback && <small className="muted">Tu comentario: {s.trainer_feedback}</small>}
        </div>)) : <Empty icon="dumbbell" title="Todavía no registró entrenamientos" />)}

      {tab === "medidas" && (measuring ? <>
        <button className="btn ghost" onClick={() => setMeasuring(false)}><Icon name="back" size={18} />Volver</button>
        <MeasureEditor member={m} last={data.measurements[0]} onSave={saveMeasure} saving={saving} draftKey={`measure:draft:${id}`} avatar={m.avatar} />
      </> : <>
        <button className="btn primary block" onClick={() => setMeasuring(true)}><Icon name="body" size={18} />Tomar medidas (3D)</button>
        {data.measurements.length ? <>
          <div className="card"><div className="sec-head"><h3>Evolución</h3></div>
            <LineChart points={[...data.measurements].reverse().map((x) => ({ x: x.date, y: x.body_fat }))} unit="%" /></div>
          <div className="card"><h3>Última · {dateShort(data.measurements[0].date)}</h3><Results r={data.measurements[0].results} sex={m.sex} /></div>
          <div className="card list">{data.measurements.map((x) => (
            <div key={x.id} className="li"><span><b>{dateShort(x.date)}</b><br /><small className="muted">{x.recorded_by || "el alumno"}</small></span>
              <span className="right"><b>{x.weight_kg ?? "—"} kg</b><br /><small>{x.body_fat ?? "—"}% · cintura {x.waist ?? "—"}</small></span></div>))}</div>
        </> : <Empty icon="body" title="Sin mediciones" />}
      </>)}

      {tab === "notas" && <>
        <div className="card stack">
          <textarea className="input" placeholder="Escribí una nota o un mensaje…" value={note.text} onChange={(e) => setNote({ ...note, text: e.target.value })} />
          <label className="row"><input type="checkbox" checked={note.visible_to_member} onChange={(e) => setNote({ ...note, visible_to_member: e.target.checked })} />
            <span>Enviarla al alumno (le llega notificación)</span></label>
          <button className="btn primary" onClick={sendNote}>Guardar</button>
        </div>
        {data.notes.map((n) => <div key={n.id} className="card"><p>{n.text}</p><small className="muted">{n.author} · {ago(n.date)}{n.visible_to_member ? " · enviada" : " · privada"}</small></div>)}
      </>}

      <Sheet open={!!exHist} onClose={() => setExHist(null)} title={exHist?.exercise?.name || exHist?.name} tall>
        {exHist?.history ? <HistoryView data={exHist} /> : <Loader />}
      </Sheet>
    </div>
  );
}

function TemplatePicker({ open, onClose, onPick }) {
  const { data } = useApi(open ? "/routines/?templates=1" : null);
  return (
    <Sheet open={open} onClose={onClose} title="Elegí una plantilla" tall>
      {!data ? <Loader /> : data.results.length ? <div className="list">{data.results.map((t) => (
        <button key={t.id} className="li" onClick={() => onPick(t)}><span style={{ textAlign: "left" }}><b>{t.name}</b><br />
          <small className="muted">{t.days.length} días · {t.goal}</small></span><Icon name="copy" size={18} /></button>))}</div>
        : <Empty icon="list" title="No hay plantillas">Creá una desde «Rutinas» marcándola como plantilla.</Empty>}
    </Sheet>
  );
}
