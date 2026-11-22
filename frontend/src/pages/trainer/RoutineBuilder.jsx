import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { Field, Loader, Sheet, Stepper } from "../../components/ui";
import { api, post, put } from "../../lib/api";
import { mmss, today } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { ExercisePicker } from "../student/Workout";

let seq = 0;
const k = () => `k${++seq}`;
const REST = [30, 45, 60, 75, 90, 120, 150, 180, 240];

function fromRoutine(r) {
  return {
    name: r.name, goal: r.goal, notes: r.notes, member: r.member, member_name: r.member_name, is_template: r.is_template,
    start_date: r.start_date || today(), end_date: r.end_date || "",
    days: r.days.map((d) => ({ key: k(), name: d.name, notes: d.notes, exercises: d.exercises.map((e) => ({
      key: k(), exercise: e.exercise, sets: e.sets, reps_min: e.reps_min ?? "", reps_max: e.reps_max ?? "",
      to_failure: e.to_failure, target_weight: e.target_weight ?? "", rest_seconds: e.rest_seconds || 90, tempo: e.tempo,
      rpe_target: e.rpe_target ?? "", superset_group: e.superset_group, notes: e.notes, duration_seconds: e.duration_seconds ?? "",
    })) })),
  };
}

const blank = (member) => ({ name: "", goal: "", notes: "", member: member || null, member_name: "", is_template: !member,
  start_date: today(), end_date: "", days: [{ key: k(), name: "Día A", notes: "", exercises: [] }] });

export default function RoutineBuilder() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const [r, setR] = useState(null);
  const [di, setDi] = useState(0);
  const [picker, setPicker] = useState(false);
  const [open, setOpen] = useState(null);
  const [saving, setSaving] = useState(false);
  const [memberPick, setMemberPick] = useState(false);

  useEffect(() => {
    (async () => {
      if (id) setR(fromRoutine(await api(`/routines/${id}/`)));
      else if (sp.get("template")) {
        const t = fromRoutine(await api(`/routines/${sp.get("template")}/`));
        setR({ ...t, member: sp.get("member") || null, is_template: !sp.get("member") });
      } else {
        const b = blank(sp.get("member"));
        if (b.member) {
          try { const d = await api(`/trainer/students/${b.member}/`); b.member_name = d.member.name; b.goal = d.member.goal_label; } catch { /* */ }
        }
        setR(b);
      }
    })().catch((e) => toast(e.message, "error"));
  }, [id, sp, toast]);

  if (!r) return <Loader />;
  const day = r.days[di] || r.days[0];
  const setDay = (patch) => setR({ ...r, days: r.days.map((d, i) => (i === di ? { ...d, ...patch } : d)) });
  const setEx = (ei, patch) => setDay({ exercises: day.exercises.map((e, i) => (i === ei ? { ...e, ...patch } : e)) });
  const move = (ei, dir) => {
    const ex = [...day.exercises]; const j = ei + dir;
    if (j < 0 || j >= ex.length) return;
    [ex[ei], ex[j]] = [ex[j], ex[ei]]; setDay({ exercises: ex });
  };
  const addDay = () => {
    const letter = String.fromCharCode(65 + r.days.length);
    setR({ ...r, days: [...r.days, { key: k(), name: `Día ${letter}`, notes: "", exercises: [] }] }); setDi(r.days.length);
  };
  const dupDay = () => {
    const copy = { ...day, key: k(), name: `${day.name} (copia)`, exercises: day.exercises.map((e) => ({ ...e, key: k() })) };
    setR({ ...r, days: [...r.days, copy] }); setDi(r.days.length);
  };
  const delDay = () => {
    if (r.days.length === 1 || !confirm(`¿Eliminar ${day.name}?`)) return;
    setR({ ...r, days: r.days.filter((_, i) => i !== di) }); setDi(0);
  };
  const addExercise = (ex) => {
    const time = ex.tracking === "time" || ex.tracking === "distance_time";
    setDay({ exercises: [...day.exercises, { key: k(), exercise: ex, sets: 3, reps_min: time ? "" : 8, reps_max: time ? "" : 12,
      to_failure: false, target_weight: "", rest_seconds: 90, tempo: "", rpe_target: "", superset_group: "", notes: "",
      duration_seconds: time ? 45 : "" }] });
    toast(`${ex.name} agregado`, "success", 1500);
  };

  const save = async () => {
    if (!r.name.trim()) return toast("Poné un nombre a la rutina", "error");
    if (!r.is_template && !r.member) return toast("Elegí el alumno o marcala como plantilla", "error");
    if (!r.days.some((d) => d.exercises.length)) return toast("Agregá al menos un ejercicio", "error");
    const n = (v) => (v === "" || v == null ? null : Number(v));
    const payload = {
      name: r.name, goal: r.goal, notes: r.notes, member: r.is_template ? null : r.member, is_template: r.is_template,
      start_date: r.start_date, end_date: r.end_date || null, is_active: !r.is_template,
      days: r.days.map((d) => ({ name: d.name, notes: d.notes, exercises: d.exercises.map((e) => ({
        exercise: e.exercise.id, sets: n(e.sets) || 1, reps_min: n(e.reps_min), reps_max: n(e.reps_max), to_failure: e.to_failure,
        target_weight: n(e.target_weight), rest_seconds: n(e.rest_seconds), tempo: e.tempo, rpe_target: n(e.rpe_target),
        superset_group: e.superset_group, notes: e.notes, duration_seconds: n(e.duration_seconds),
      })) })),
    };
    setSaving(true);
    try {
      const res = id ? await put(`/routines/${id}/`, payload) : await post("/routines/", payload);
      toast(res.version > 1 && id && String(res.id) !== String(id) ? `Guardada como versión ${res.version}` : "Rutina guardada", "success");
      nav(r.is_template ? "/entrenador/rutinas" : `/entrenador/alumnos/${r.member}?tab=rutinas`);
    } catch (e) { toast(e.message, "error"); } finally { setSaving(false); }
  };

  return (
    <div className="page-pad stack builder">
      <div className="row between"><h1 className="title">{id ? "Editar rutina" : "Nueva rutina"}</h1>
        <button className="btn primary" disabled={saving} onClick={save}>{saving ? "Guardando…" : "Guardar"}</button></div>

      <div className="card stack">
        <Field label="Nombre"><input className="input" value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} placeholder="Ej: Hipertrofia PPL" /></Field>
        <div className="grid2">
          <Field label="Objetivo"><input className="input" value={r.goal} onChange={(e) => setR({ ...r, goal: e.target.value })} /></Field>
          <Field label="Desde"><input type="date" className="input" value={r.start_date} onChange={(e) => setR({ ...r, start_date: e.target.value })} /></Field>
        </div>
        <label className="row"><input type="checkbox" checked={r.is_template} onChange={(e) => setR({ ...r, is_template: e.target.checked })} /><span>Es una plantilla (reutilizable)</span></label>
        {!r.is_template && <button className="li member-pick" onClick={() => setMemberPick(true)}>
          <span><small className="muted">Alumno</small><br /><b>{r.member_name || (r.member ? `#${r.member}` : "Elegir alumno")}</b></span><Icon name="next" size={18} /></button>}
        <Field label="Indicaciones generales"><textarea className="input" value={r.notes} onChange={(e) => setR({ ...r, notes: e.target.value })} placeholder="Calentamiento, cardio, progresión…" /></Field>
        {id && <small className="muted"><Icon name="info" size={14} /> Si el alumno ya entrenó con esta rutina, se guarda como una versión nueva y el historial queda intacto.</small>}
      </div>

      <div className="chips-scroll">
        {r.days.map((d, i) => <button key={d.key} className={`chip ${i === di ? "on" : ""}`} onClick={() => setDi(i)}>{d.name} <small>({d.exercises.length})</small></button>)}
        <button className="chip" onClick={addDay}><Icon name="plus" size={14} />Día</button>
      </div>

      <div className="card stack">
        <div className="row">
          <input className="input" value={day.name} onChange={(e) => setDay({ name: e.target.value })} />
          <button className="icon-btn" onClick={dupDay} title="Duplicar día"><Icon name="copy" size={18} /></button>
          <button className="icon-btn" onClick={delDay} title="Eliminar día"><Icon name="trash" size={18} /></button>
        </div>
        <input className="input" placeholder="Notas del día (opcional)" value={day.notes} onChange={(e) => setDay({ notes: e.target.value })} />
      </div>

      {day.exercises.map((e, ei) => {
        const time = e.exercise.tracking === "time" || e.exercise.tracking === "distance_time";
        const exp = open === e.key;
        return (
          <div key={e.key} className={`card bx ${e.superset_group ? "superset" : ""}`}>
            <div className="bx-head">
              <span className="num">{e.superset_group || ei + 1}</span>
              <div style={{ flex: 1 }}><b>{e.exercise.name}</b><br /><small className="muted">{e.exercise.muscle_label}</small></div>
              <button className="icon-btn" onClick={() => move(ei, -1)}><Icon name="up" size={18} /></button>
              <button className="icon-btn" onClick={() => move(ei, 1)}><Icon name="down" size={18} /></button>
              <button className="icon-btn" onClick={() => setDay({ exercises: day.exercises.filter((_, i) => i !== ei) })}><Icon name="trash" size={18} /></button>
            </div>
            <div className="bx-grid">
              <Field label="Series"><Stepper value={e.sets} onChange={(v) => setEx(ei, { sets: v })} inputMode="numeric" min={1} /></Field>
              {time ? <Field label="Segundos"><Stepper value={e.duration_seconds} onChange={(v) => setEx(ei, { duration_seconds: v })} step={5} inputMode="numeric" /></Field> : <>
                <Field label="Reps mín."><Stepper value={e.reps_min} onChange={(v) => setEx(ei, { reps_min: v })} inputMode="numeric" /></Field>
                <Field label="Reps máx."><Stepper value={e.reps_max} onChange={(v) => setEx(ei, { reps_max: v })} inputMode="numeric" /></Field>
                <Field label="Kg sugeridos"><Stepper value={e.target_weight} onChange={(v) => setEx(ei, { target_weight: v })} step={2.5} /></Field>
              </>}
              <Field label="Descanso"><select className="input" value={e.rest_seconds} onChange={(ev) => setEx(ei, { rest_seconds: Number(ev.target.value) })}>
                {REST.map((s) => <option key={s} value={s}>{mmss(s)}</option>)}</select></Field>
              <button className={`toggle ${e.to_failure ? "on" : ""}`} onClick={() => setEx(ei, { to_failure: !e.to_failure })}>Al fallo</button>
            </div>
            <button className="btn sm ghost" onClick={() => setOpen(exp ? null : e.key)}>{exp ? "Menos opciones" : "Más opciones (tempo, RPE, superserie, notas)"}</button>
            {exp && <div className="bx-grid">
              <Field label="Tempo"><input className="input" value={e.tempo} placeholder="3-1-1-0" onChange={(ev) => setEx(ei, { tempo: ev.target.value })} /></Field>
              <Field label="RPE objetivo"><Stepper value={e.rpe_target} onChange={(v) => setEx(ei, { rpe_target: v })} step={0.5} /></Field>
              <Field label="Superserie" hint="Misma letra = se hacen juntos"><input className="input" maxLength={2} value={e.superset_group} onChange={(ev) => setEx(ei, { superset_group: ev.target.value.toUpperCase() })} /></Field>
              <Field label="Notas"><input className="input" value={e.notes} onChange={(ev) => setEx(ei, { notes: ev.target.value })} placeholder="Agarre, técnica…" /></Field>
            </div>}
          </div>
        );
      })}
      <button className="btn block dashed" onClick={() => setPicker(true)}><Icon name="plus" size={18} />Agregar ejercicio a {day.name}</button>
      <button className="btn primary lg block" disabled={saving} onClick={save}>{saving ? "Guardando…" : "Guardar rutina"}</button>

      <ExercisePicker open={picker} onClose={() => setPicker(false)} onPick={addExercise} />
      <MemberPicker open={memberPick} onClose={() => setMemberPick(false)} onPick={(m) => { setR({ ...r, member: m.id, member_name: m.name }); setMemberPick(false); }} />
    </div>
  );
}

function MemberPicker({ open, onClose, onPick }) {
  const { data } = useApi(open ? "/trainer/students/" : null);
  const [q, setQ] = useState("");
  const list = (data?.results || []).filter((s) => !q || s.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <Sheet open={open} onClose={onClose} title="Elegí el alumno" tall>
      <div className="search-box"><Icon name="search" size={18} /><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar" autoFocus /></div>
      {!data ? <Loader /> : <div className="list">{list.map((s) => (
        <button key={s.id} className="li" onClick={() => onPick(s)}><span style={{ textAlign: "left" }}><b>{s.name}</b><br /><small className="muted">{s.goal_label}{s.routine ? ` · rutina: ${s.routine.name}` : " · sin rutina"}</small></span><Icon name="next" size={18} /></button>))}</div>}
    </Sheet>
  );
}
