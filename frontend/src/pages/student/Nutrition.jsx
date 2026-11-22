import { useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LineChart } from "../../components/Charts";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { Empty, Field, Loader, Ring, Segmented } from "../../components/ui";
import { api, post } from "../../lib/api";
import { dateLong, dateShort, num, today } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { guessMeal } from "../../lib/nutrition";
import AddFoodSheet from "./nutrition/AddFoodSheet";
import { MacroBars, MacroLine } from "./nutrition/parts";
import Review, { draftFromMeal } from "./nutrition/Review";

const shift = (d, n) => { const x = new Date(d + "T12:00:00"); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10); };

export default function Nutrition() {
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") || "dia";
  const setTab = (t) => setSp(t === "dia" ? {} : { tab: t }, { replace: true });
  return (
    <div className="page-pad stack">
      <div className="row between"><h1 className="title">Nutrición</h1></div>
      <Segmented value={tab} onChange={setTab} options={[["dia", "Mi día"], ["progreso", "Progreso"], ["metas", "Metas"]]} />
      {tab === "dia" && <Day onGoals={() => setTab("metas")} />}
      {tab === "progreso" && <Stats />}
      {tab === "metas" && <Goals onDone={() => setTab("dia")} />}
    </div>
  );
}

// ------------------------------------------------------------------ día
function Day({ onGoals }) {
  const toast = useToast();
  const [date, setDate] = useState(today());
  const { data, loading, reload } = useApi(`/me/nutrition/day/?date=${date}`);
  const [adding, setAdding] = useState(null);
  const [draft, setDraft] = useState(null);

  const onDraft = useCallback((d) => { setDraft({ ...d, meal_type: adding, date }); setAdding(null); }, [adding, date]);
  const done = () => { setDraft(null); setAdding(null); reload(); };
  const isToday = date === today();

  const copyDay = async () => {
    try { await post("/me/nutrition/copy/", { from_date: shift(date, -1), to_date: date }); toast("Copiamos las comidas de ayer", "ok"); reload(); }
    catch (e) { toast(e.message, "bad"); }
  };

  if (loading && !data) return <Loader />;
  if (!data) return <Empty icon="food" title="No pudimos cargar tus comidas">Revisá la conexión y volvé a intentar.</Empty>;
  const t = data.targets, tot = data.totals;
  const empty = data.groups.every((g) => !g.meals.length);
  const left = t ? Math.round(t.kcal - tot.kcal) : null;

  return (
    <>
      <div className="date-nav">
        <button className="icon-btn" onClick={() => setDate(shift(date, -1))} aria-label="Día anterior"><Icon name="back" /></button>
        <button className="date-label" onClick={() => setDate(today())}><b>{isToday ? "Hoy" : date === shift(today(), -1) ? "Ayer" : dateLong(date)}</b>
          {data.streak > 1 && <span className="pill xs"><Icon name="fire" size={13} className="c-fire" />{data.streak} días</span>}</button>
        <button className="icon-btn" disabled={isToday} onClick={() => setDate(shift(date, 1))} aria-label="Día siguiente"><Icon name="next" /></button>
      </div>

      {!data.profile_ready ? (
        <button className="card tip action" onClick={onGoals}><Icon name="target" size={20} />
          <span><b>Configurá tus metas</b><br /><small>Con tu peso, altura y objetivo calculamos tus calorías y macros.</small></span><Icon name="next" /></button>
      ) : (
        <div className="card nutri-summary">
          <Ring value={tot.kcal} max={t.kcal} size={124} stroke={12} color={tot.kcal > t.kcal * 1.1 ? "var(--bad)" : "var(--brand)"}
            label={num(tot.kcal, 0)} sub={`de ${t.kcal} kcal`} />
          <div className="grow">
            <p className="kcal-left">{left >= 0 ? <>Te quedan <b>{left}</b> kcal</> : <>Te pasaste <b className="c-bad">{-left}</b> kcal</>}</p>
            <MacroBars totals={tot} targets={t} compact />
          </div>
        </div>
      )}
      {data.trainer_notes && <div className="card tip"><Icon name="msg" size={18} /><span><b>Tu entrenador:</b> {data.trainer_notes}</span></div>}

      {data.groups.map((g) => (
        <div key={g.meal_type} className="card meal-card">
          <div className="row between">
            <div><b>{g.label}</b>{g.totals && <small className="muted"> · {num(g.totals.kcal, 0)} kcal</small>}</div>
            <button className="btn sm" onClick={() => setAdding(g.meal_type)}><Icon name="plus" size={16} />Agregar</button>
          </div>
          {g.meals.map((m) => (
            <button key={m.id} className="meal-entry" onClick={() => setDraft(draftFromMeal(m))}>
              {m.image ? <img src={m.image} alt="" /> : <span className="meal-ico"><Icon name={m.source === "barcode" ? "barcode" : m.source === "saved" ? "bookmark" : "food"} size={18} /></span>}
              <span className="grow">{m.items.map((i) => <span key={i.id} className="meal-item">{i.name} <small className="muted">{num(i.grams, 0)} g · {num(i.kcal, 0)} kcal</small></span>)}</span>
              <Icon name="edit" size={16} />
            </button>
          ))}
        </div>
      ))}

      {empty && <div className="row center-row">
        <button className="btn" onClick={copyDay}><Icon name="repeat" size={18} />Copiar todo lo de ayer</button>
        {isToday && <button className="btn primary" onClick={() => setAdding(guessMeal())}><Icon name="camera" size={18} />Cargar comida</button>}
      </div>}

      <AddFoodSheet open={!!adding} onClose={() => setAdding(null)} mealType={adding} date={date} ai={data.ai}
        onDraft={onDraft} onLogged={done} />
      <Review draft={draft} onClose={() => setDraft(null)} onSaved={done} />
    </>
  );
}

// ------------------------------------------------------------------ progreso
function Stats() {
  const [days, setDays] = useState(30);
  const { data, loading } = useApi(`/me/nutrition/stats/?days=${days}`);
  if (loading && !data) return <Loader />;
  if (!data) return null;
  const a = data.adherence, t = data.targets;
  const logged = data.days.filter((d) => d.kcal != null);
  if (!logged.length) return <Empty icon="chart" title="Todavía no hay datos">Registrá tus comidas unos días y acá vas a ver tus promedios y cómo se relacionan con tu peso.</Empty>;
  const dot = { ok: "ok", mid: "warn", bad: "bad", logged: "info" };
  return (
    <>
      <Segmented value={days} onChange={setDays} options={[[7, "7 días"], [30, "30 días"], [90, "90 días"]]} />
      <div className="grid3">
        <div className="stat"><span className="stat-label">Racha</span><b className="stat-value">{data.streak}</b><small>días seguidos</small></div>
        <div className="stat"><span className="stat-label">Promedio 7 días</span><b className="stat-value">{a.avg ? num(a.avg.kcal, 0) : "—"}</b><small>{a.kcal_pct ? `${a.kcal_pct}% de la meta` : "kcal"}</small></div>
        <div className="stat"><span className="stat-label">Proteína</span><b className="stat-value">{a.avg ? num(a.avg.protein, 0) : "—"} g</b><small>{a.protein_pct ? `${a.protein_pct}% de la meta` : "promedio"}</small></div>
      </div>
      <div className="card">
        <b>Última semana</b>
        <div className="week-dots">{a.statuses.map((s, i) => <i key={i} className={s ? dot[s] : ""} />)}</div>
        <small className="muted">Verde: calorías dentro del ±10 % y proteína cumplida · Amarillo: una de las dos · Gris: sin registro</small>
      </div>
      <div className="card"><b>Calorías por día</b>
        <LineChart points={logged.map((d) => ({ x: d.date, y: d.kcal }))} unit=" kcal" yFormat={(v) => num(v, 0)} />
        {t && <small className="muted">Meta: {t.kcal} kcal</small>}</div>
      <div className="card"><b>Peso</b>
        {data.weight.length ? <LineChart points={data.weight.map((w) => ({ x: w.date, y: w.weight }))} unit=" kg" color="var(--info)" />
          : <p className="muted">Cargá tu peso en «Cuerpo» para compararlo con lo que comés.</p>}</div>
      {data.weeks.length > 1 && (
        <div className="card"><b>Promedio semanal</b>
          <table className="table"><thead><tr><th>Semana</th><th>Días</th><th>kcal</th><th>Prot.</th></tr></thead>
            <tbody>{data.weeks.map((w) => <tr key={w.start}><td>{dateShort(w.start)}</td><td>{w.days_logged}</td><td>{w.avg_kcal}</td><td>{w.avg_protein} g</td></tr>)}</tbody></table>
          <small className="muted">El promedio semanal dice más que un día aislado.</small></div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ metas
function Goals({ onDone }) {
  const toast = useToast();
  const { data, loading, setData } = useApi("/me/nutrition/profile/", { cache: false });
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  if (loading && !data) return <Loader />;
  if (!data) return null;
  const f = form || { goal: data.goal, pace: data.pace, activity: data.activity, weight_kg: data.weight_kg ?? "", height_cm: "", birth_date: "" };
  const set = (k, v) => setForm({ ...f, [k]: v });
  const save = async () => {
    setSaving(true);
    try {
      const d = await api("/me/nutrition/profile/", { method: "PUT", body: f });
      setData(d); setForm(null); toast("Metas actualizadas", "ok");
      if (d.targets) onDone();
    } catch (e) { toast(e.message, "bad"); } finally { setSaving(false); }
  };
  const t = data.targets, s = data.suggestion, b = data.body;
  return (
    <>
      {data.is_custom && <div className="card tip"><Icon name="info" size={18} /><span>Tu entrenador fijó tus metas{data.updated_by ? ` (${data.updated_by})` : ""}. Podés cambiar tu objetivo, pero las calorías y macros las ajusta él.</span></div>}
      {t && (
        <div className="card">
          <b>Tu meta diaria</b>
          <div className="goal-grid">
            <div><b>{t.kcal}</b><small>kcal</small></div><div><b>{t.protein} g</b><small>proteínas</small></div>
            <div><b>{t.carbs} g</b><small>carbohidratos</small></div><div><b>{t.fat} g</b><small>grasas</small></div>
          </div>
          {s && !data.is_custom && <small className="muted">Gasto estimado: {s.tdee} kcal/día (metabolismo basal {s.bmr} kcal, fórmula Mifflin-St Jeor).</small>}
        </div>
      )}
      <div className="card stack">
        <Field label="Objetivo"><div className="seg">{data.choices.goal.map(([v, l]) => <button key={v} type="button" className={f.goal === v ? "on" : ""} onClick={() => set("goal", v)}>{l}</button>)}</div></Field>
        {f.goal !== "maintain" && <Field label="Ritmo" hint={f.goal === "cut" ? "Suave: −10 % · Moderado: −20 % · Agresivo: −25 % de tu gasto" : "Suave: +5 % · Moderado: +10 % · Agresivo: +15 % de tu gasto"}>
          <div className="seg">{data.choices.pace.map(([v, l]) => <button key={v} type="button" className={f.pace === v ? "on" : ""} onClick={() => set("pace", v)}>{l}</button>)}</div></Field>}
        <Field label="Nivel de actividad"><select className="input" value={f.activity} onChange={(e) => set("activity", e.target.value)}>
          {data.choices.activity.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        {!b.weight_from_measurement && <Field label="Peso (kg)" hint="Si cargás tus medidas en «Cuerpo», usamos la última."><input className="input" inputMode="decimal" value={f.weight_kg} onChange={(e) => set("weight_kg", e.target.value.replace(",", "."))} /></Field>}
        {data.missing.includes("altura") && <Field label="Altura (cm)"><input className="input" inputMode="numeric" value={f.height_cm} onChange={(e) => set("height_cm", e.target.value)} /></Field>}
        {data.missing.includes("fecha de nacimiento") && <Field label="Fecha de nacimiento"><input className="input" type="date" value={f.birth_date} onChange={(e) => set("birth_date", e.target.value)} /></Field>}
        {b.weight_from_measurement && <small className="muted">Peso: {num(b.weight_kg)} kg · Altura: {num(b.height_cm, 0)} cm · Edad: {b.age} años{b.body_fat ? ` · Grasa: ${num(b.body_fat)} %` : ""}</small>}
        <button className="btn primary block" disabled={saving} onClick={save}>{saving ? "Calculando…" : "Calcular mis metas"}</button>
      </div>
      <small className="muted block">Las metas son una estimación general para personas sanas. Si tenés alguna condición médica, consultá con un profesional de la nutrición.</small>
    </>
  );
}
