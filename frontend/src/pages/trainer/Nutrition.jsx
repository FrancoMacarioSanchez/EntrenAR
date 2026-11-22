import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { LineChart } from "../../components/Charts";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { Avatar, Empty, Field, Loader } from "../../components/ui";
import { api } from "../../lib/api";
import { dateLong, num } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { MacroBars, MacroLine } from "../student/nutrition/parts";

const COLOR = { green: ["Cumple", "ok"], yellow: ["Irregular", "warn"], red: ["No cumple", "bad"] };
const DOT = { ok: "ok", mid: "warn", bad: "bad", logged: "info" };

// Semáforo de adherencia de los alumnos.
export function NutritionBoard() {
  const { data, loading } = useApi("/trainer/nutrition/");
  const [filter, setFilter] = useState("all");
  if (loading && !data) return <Loader />;
  if (!data) return null;
  const list = filter === "all" ? data : data.filter((s) => s.adherence.color === filter);
  const count = (c) => data.filter((s) => s.adherence.color === c).length;
  return (
    <div className="page-pad stack">
      <h1 className="title">Nutrición</h1>
      <div className="chips-scroll">
        <button className={`chip ${filter === "all" ? "on" : ""}`} onClick={() => setFilter("all")}>Todos ({data.length})</button>
        {["red", "yellow", "green"].map((c) => <button key={c} className={`chip ${filter === c ? "on" : ""}`} onClick={() => setFilter(c)}><i className={`dot ${COLOR[c][1]}`} />{COLOR[c][0]} ({count(c)})</button>)}
      </div>
      {!list.length ? <Empty icon="food" title="Sin alumnos acá">Aparecen los alumnos que registraron comidas en los últimos 30 días.</Empty> : list.map((s) => (
        <Link key={s.id} to={`/entrenador/nutricion/${s.id}`} className="card student-row">
          <Avatar src={s.photo} initials={s.initials} size={42} />
          <span className="grow"><b>{s.name}</b><br />
            <small className="muted">{s.adherence.days_logged}/7 días registrados
              {s.adherence.kcal_pct != null && ` · ${s.adherence.kcal_pct}% kcal`}{s.adherence.protein_pct != null && ` · ${s.adherence.protein_pct}% prot.`}</small>
            <span className="week-dots sm">{s.adherence.statuses.map((x, i) => <i key={i} className={x ? DOT[x] : ""} />)}</span></span>
          <span className={`pill ${COLOR[s.adherence.color][1]}`}>{COLOR[s.adherence.color][0]}</span>
        </Link>
      ))}
    </div>
  );
}

// Detalle de un alumno: metas (automáticas o fijadas por el entrenador), evolución y comidas recientes.
export function StudentNutrition() {
  const { id } = useParams();
  const toast = useToast();
  const { data, loading, setData } = useApi(`/trainer/students/${id}/nutrition/`, { cache: false });
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  if (loading && !data) return <Loader />;
  if (!data) return null;
  const p = data.profile, m = data.member, t = p.targets;
  const f = form || { calories: t?.kcal ?? p.suggestion?.kcal ?? "", protein_g: t?.protein ?? "", carbs_g: t?.carbs ?? "", fat_g: t?.fat ?? "",
    goal: p.goal, activity: p.activity, pace: p.pace, trainer_notes: p.trainer_notes };
  const set = (k, v) => setForm({ ...f, [k]: v });
  const kcalFromMacros = Math.round((Number(f.protein_g) || 0) * 4 + (Number(f.carbs_g) || 0) * 4 + (Number(f.fat_g) || 0) * 9);

  const save = async (reset = false) => {
    setSaving(true);
    try {
      const d = await api(`/trainer/students/${id}/nutrition/`, { method: "PUT", body: reset ? { reset: true, goal: f.goal, activity: f.activity, pace: f.pace, trainer_notes: f.trainer_notes } : f });
      setData(d); setForm(null); toast(reset ? "Volvió al cálculo automático" : "Metas guardadas y avisadas al alumno", "ok");
    } catch (e) { toast(e.message, "bad"); } finally { setSaving(false); }
  };

  const logged = data.stats.days.filter((d) => d.kcal != null);
  return (
    <div className="page-pad stack">
      <Link to={`/entrenador/alumnos/${m.id}`} className="row"><Avatar src={m.photo} initials={m.initials} size={44} />
        <span><b>{m.name}</b><br /><small className="muted">{p.body.age ? `${p.body.age} años · ` : ""}{p.body.weight_kg ? `${num(p.body.weight_kg)} kg` : "sin peso"}{data.streak ? ` · racha ${data.streak} días` : ""}</small></span></Link>

      <div className="card">
        <div className="row between"><b>Últimos 7 días</b><span className={`pill ${COLOR[data.adherence.color][1]}`}>{COLOR[data.adherence.color][0]}</span></div>
        <div className="week-dots">{data.adherence.statuses.map((x, i) => <i key={i} className={x ? DOT[x] : ""} />)}</div>
        {data.adherence.avg && <MacroLine m={data.adherence.avg} />}
      </div>

      <div className="card stack">
        <div className="row between"><b>Metas diarias</b>{p.is_custom ? <span className="pill info">Fijadas por entrenador</span> : <span className="pill">Automáticas</span>}</div>
        {p.suggestion && <small className="muted">Cálculo automático: {p.suggestion.kcal} kcal · P {p.suggestion.protein} · C {p.suggestion.carbs} · G {p.suggestion.fat} (gasto {p.suggestion.tdee} kcal)</small>}
        {p.missing.length > 0 && <small className="warn">Para el cálculo automático falta: {p.missing.join(", ")}.</small>}
        <div className="grid2">
          <Field label="Calorías"><input className="input" inputMode="numeric" value={f.calories} onChange={(e) => set("calories", e.target.value)} /></Field>
          <Field label="Proteínas (g)"><input className="input" inputMode="numeric" value={f.protein_g} onChange={(e) => set("protein_g", e.target.value)} /></Field>
          <Field label="Carbohidratos (g)"><input className="input" inputMode="numeric" value={f.carbs_g} onChange={(e) => set("carbs_g", e.target.value)} /></Field>
          <Field label="Grasas (g)"><input className="input" inputMode="numeric" value={f.fat_g} onChange={(e) => set("fat_g", e.target.value)} /></Field>
        </div>
        {kcalFromMacros > 0 && Math.abs(kcalFromMacros - Number(f.calories)) > 50 && <small className="warn">Los macros suman {kcalFromMacros} kcal (no coincide con las calorías).</small>}
        <div className="grid2">
          <Field label="Objetivo"><select className="input" value={f.goal} onChange={(e) => set("goal", e.target.value)}>{p.choices.goal.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
          <Field label="Actividad"><select className="input" value={f.activity} onChange={(e) => set("activity", e.target.value)}>{p.choices.activity.map(([v, l]) => <option key={v} value={v}>{l.split(" (")[0]}</option>)}</select></Field>
        </div>
        <Field label="Indicaciones para el alumno"><textarea className="input" rows={3} value={f.trainer_notes} onChange={(e) => set("trainer_notes", e.target.value)} placeholder="Ej: priorizá proteína en el desayuno" /></Field>
        <div className="row">
          {p.is_custom && <button className="btn" disabled={saving} onClick={() => save(true)}>Usar automático</button>}
          <button className="btn primary" style={{ flex: 1 }} disabled={saving} onClick={() => save(false)}>{saving ? "Guardando…" : "Guardar metas"}</button>
        </div>
      </div>

      <div className="card"><b>Calorías (30 días)</b>
        <LineChart points={logged.map((d) => ({ x: d.date, y: d.kcal }))} unit=" kcal" yFormat={(v) => num(v, 0)} /></div>
      {data.stats.weight.length > 1 && <div className="card"><b>Peso</b><LineChart points={data.stats.weight.map((w) => ({ x: w.date, y: w.weight }))} unit=" kg" color="var(--info)" /></div>}

      <h3>Comidas recientes</h3>
      {!data.recent.length ? <p className="muted">Todavía no registró comidas.</p> : data.recent.map((d) => (
        <div key={d.date} className="card stack">
          <div className="row between"><b>{dateLong(d.date)}</b><small><b>{num(d.totals.kcal, 0)}</b> kcal</small></div>
          {t && <MacroBars totals={d.totals} targets={t} compact />}
          {d.meals.map((meal) => (
            <div key={meal.id} className="meal-entry static">
              {meal.image ? <a href={meal.image} target="_blank" rel="noreferrer"><img src={meal.image} alt="" /></a> : <span className="meal-ico"><Icon name="food" size={18} /></span>}
              <span className="grow"><small className="muted">{meal.meal_label}</small>
                {meal.items.map((i) => <span key={i.id} className="meal-item">{i.name} <small className="muted">{num(i.grams, 0)} g · {num(i.kcal, 0)} kcal</small></span>)}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
