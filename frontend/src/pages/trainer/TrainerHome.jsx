import { Link } from "react-router-dom";
import Icon from "../../components/Icon";
import InstallPrompt from "../../components/InstallPrompt";
import { Avatar, Loader } from "../../components/ui";
import { ago, greeting, num } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { useAuth } from "../../state/auth";

export default function TrainerHome() {
  const { me } = useAuth();
  const feed = useApi("/trainer/feed/?mine=1");
  const classes = useApi("/trainer/classes/?days=2");
  const st = useApi("/trainer/students/?mine=1");
  const students = st.data?.results || [];
  const count = (f) => students.filter((s) => s.flags.includes(f)).length;
  return (
    <div className="page-pad stack">
      <section className="hello"><div><small className="muted">{greeting()}</small><h1>{me.user.first_name || me.user.username} 💪</h1></div></section>
      <div className="grid2">
        <Link to="/entrenador/alumnos" className="card kpi-sm"><small>Mis alumnos</small><b>{students.length}</b></Link>
        <Link to="/entrenador/alumnos?flag=no_entrena" className="card kpi-sm warn"><small>No entrenan hace +7 días</small><b>{count("no_entrena")}</b></Link>
        <Link to="/entrenador/alumnos?flag=sin_rutina" className="card kpi-sm bad"><small>Sin rutina</small><b>{count("sin_rutina")}</b></Link>
        <Link to="/entrenador/alumnos?flag=rutina_vieja" className="card kpi-sm info"><small>Rutina de +8 semanas</small><b>{count("rutina_vieja")}</b></Link>
      </div>
      <InstallPrompt />
      {classes.data?.results?.length > 0 && <section>
        <div className="sec-head"><h3>Tus próximas clases</h3><Link to="/entrenador/clases">Ver todas</Link></div>
        <div className="h-scroll">{classes.data.results.slice(0, 6).map((c) => (
          <Link key={c.id + c.date} to={`/entrenador/clases/${c.id}/${c.date}`} className="pr-card" style={{ borderTop: `4px solid ${c.color}` }}>
            <b>{c.time} · {c.name}</b><small className="muted">{c.date === new Date().toISOString().slice(0, 10) ? "Hoy" : "Mañana"}</small>
            <small>{c.cancelled ? "Suspendida" : `${c.booked}/${c.capacity} anotados`}</small></Link>))}</div>
      </section>}
      <div className="row"><Link className="btn primary block" to="/entrenador/rutinas/nueva"><Icon name="plus" size={18} />Nueva rutina</Link>
        <Link className="btn block" to="/entrenador/alumnos"><Icon name="users" size={18} />Alumnos</Link></div>
      {feed.loading && !feed.data ? <Loader /> : <>
        {feed.data?.records?.length > 0 && <section><div className="sec-head"><h3>🏆 Récords de la semana</h3></div>
          <div className="h-scroll">{feed.data.records.map((r) => (
            <Link key={r.id} to={`/entrenador/alumnos/${r.member}`} className="pr-card"><b>{r.member_name}</b><small>{r.exercise_name}</small><small className="c-brand">{r.label}</small></Link>))}</div></section>}
        <section className="card"><div className="sec-head"><h3>Actividad reciente</h3></div>
          {feed.data?.sessions?.length ? feed.data.sessions.map((s) => (
            <Link key={s.id} to={`/entrenador/alumnos/${s.member}?sesion=${s.id}`} className="li">
              <span className="row" style={{ gap: 10 }}><Avatar initials={s.member_name.split(" ").map((x) => x[0]).join("").slice(0, 2)} size={36} />
                <span><b>{s.member_name}</b><br /><small className="muted">{s.routine_day_name} · {s.sets_count} series · {num(s.volume / 1000, 1)} t</small></span></span>
              <span className="right"><small className="muted">{ago(s.started_at)}</small>{s.feeling && <><br />{["😫", "😕", "🙂", "💪", "🔥"][s.feeling - 1]}</>}</span></Link>))
            : <p className="muted">Tus alumnos todavía no registraron entrenamientos esta semana.</p>}</section>
      </>}
    </div>
  );
}
