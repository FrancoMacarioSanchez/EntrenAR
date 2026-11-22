import { useState } from "react";
import { Link } from "react-router-dom";
import { Bars, HBars } from "../../components/Charts";
import Icon from "../../components/Icon";
import { Empty, Loader, Segmented, Stat } from "../../components/ui";
import { ago, dateShort, num } from "../../lib/format";
import { useApi } from "../../lib/hooks";

export default function Progress() {
  const { data: p, loading } = useApi("/me/progress/");
  const sessions = useApi("/me/sessions/");
  const [tab, setTab] = useState("resumen");
  if (loading && !p) return <Loader />;
  if (!p) return null;
  return (
    <div className="page-pad stack">
      <h1 className="title">Mi progreso</h1>
      <Segmented value={tab} onChange={setTab} options={[["resumen", "Resumen"], ["ejercicios", "Ejercicios"], ["historial", "Historial"]]} />
      {tab === "resumen" && <>
        <div className="grid2">
          <div className="card"><Stat label="Entrenamientos" value={p.sessions_total} sub={`${p.sessions_month} este mes`} /></div>
          <div className="card"><Stat label="Racha" value={`${p.week_streak} sem.`} sub="seguidas" accent="#f97316" /></div>
          <div className="card"><Stat label="Volumen total" value={`${num(p.total_volume / 1000, 1)} t`} /></div>
          <div className="card"><Stat label="Ingresos (30 días)" value={p.checkins_30d} /></div>
        </div>
        <div className="card"><div className="sec-head"><h3>Volumen por semana</h3><small className="muted">kg</small></div>
          <Bars items={p.weeks.map((w) => ({ label: dateShort(w.week), value: w.volume }))} format={(v) => `${num(v, 0)} kg`} /></div>
        <div className="card"><div className="sec-head"><h3>Entrenamientos por semana</h3></div>
          <Bars items={p.weeks.map((w) => ({ label: dateShort(w.week), value: w.sessions }))} color="#22c55e" /></div>
        {Object.keys(p.muscles_30d).length > 0 && <div className="card"><div className="sec-head"><h3>Series por músculo (30 días)</h3></div>
          <HBars items={Object.entries(p.muscles_30d).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value }))} /></div>}
        <section className="card"><div className="sec-head"><h3>🏆 Récords personales</h3></div>
          {p.records.length ? <div className="list">{p.records.map((r) => (
            <Link key={r.id} to={`/progreso/ejercicio/${r.exercise}`} className="li"><span><b>{r.exercise_name}</b><br /><small className="muted">{r.kind_label} · {ago(r.achieved_at)}</small></span><b className="c-brand">{r.label}</b></Link>))}</div>
            : <p className="muted">Cuando superes una marca la vas a ver acá.</p>}</section>
        {p.achievements.length > 0 && <section className="card"><div className="sec-head"><h3>Logros</h3></div>
          <div className="badges">{p.achievements.map((a) => <span key={a.code} className="ach" title={a.description}><i>{a.icon}</i>{a.title}</span>)}</div></section>}
      </>}
      {tab === "ejercicios" && (p.exercises.length ? <div className="card list">{p.exercises.map((e) => (
        <Link key={e.id} to={`/progreso/ejercicio/${e.id}`} className="li"><span><b>{e.name}</b><br /><small className="muted">{e.sets} series · último {dateShort(e.last)}</small></span>
          <span className="row">{e.top_weight ? <b>{e.top_weight} kg</b> : null}<Icon name="next" size={18} /></span></Link>))}</div>
        : <Empty icon="dumbbell" title="Sin registros todavía" />)}
      {tab === "historial" && (sessions.data?.results?.length ? <div className="card list">{sessions.data.results.map((s) => (
        <Link key={s.id} to={`/progreso/sesion/${s.id}`} className="li"><span><b>{s.routine_day_name}</b><br />
          <small className="muted">{dateShort(s.date)} · {s.sets_count} series · {num(s.volume / 1000, 1)} t{s.duration_min ? ` · ${s.duration_min} min` : ""}</small></span>
          <span className="row">{s.trainer_feedback && <Icon name="msg" size={18} className="c-brand" />}<Icon name="next" size={18} /></span></Link>))}</div>
        : <Empty icon="list" title="Sin entrenamientos" />)}
    </div>
  );
}
