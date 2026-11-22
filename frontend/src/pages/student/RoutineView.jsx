import { useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../../components/Icon";
import { Empty, Loader, Sheet } from "../../components/ui";
import { dateShort, mmss } from "../../lib/format";
import { useApi } from "../../lib/hooks";

export default function RoutineView() {
  const { data, loading } = useApi("/me/routine/");
  const [ex, setEx] = useState(null);
  const r = data?.routine;
  if (loading && !data) return <Loader />;
  if (!r) return <div className="page-pad"><Empty icon="list" title="Todavía no tenés rutina">Tu entrenador la va a cargar en la app y te va a llegar una notificación.</Empty></div>;
  return (
    <div className="page-pad stack">
      <div><h1 className="title">{r.name}</h1>
        <small className="muted">{r.goal && `${r.goal} · `}por {r.trainer || "tu entrenador"} · desde {dateShort(r.start_date)} · v{r.version}</small></div>
      {r.notes && <div className="card tip"><Icon name="msg" size={18} />{r.notes}</div>}
      {r.days.map((d) => (
        <section key={d.id} className="card">
          <div className="sec-head"><h3>{d.name}</h3><Link className="btn sm primary" to={`/entrenar/${d.id}`}><Icon name="play" size={16} />Entrenar</Link></div>
          {d.notes && <p className="muted">{d.notes}</p>}
          <div className="list">{d.exercises.map((e, i) => (
            <button key={e.id} className="li" onClick={() => setEx(e)}>
              <span className="row" style={{ gap: 12 }}><span className="num">{e.superset_group || i + 1}</span>
                <span style={{ textAlign: "left" }}><b>{e.exercise.name}</b><br />
                  <small className="muted">{e.sets} × {e.reps_label || "—"}{e.target_weight ? ` · ${e.target_weight} kg` : ""}{e.rest_seconds ? ` · ${mmss(e.rest_seconds)}` : ""}</small></span></span>
              <Icon name="info" size={18} /></button>))}</div>
        </section>
      ))}
      <Sheet open={!!ex} onClose={() => setEx(null)} title={ex?.exercise.name}>
        {ex && <div className="stack">
          <div className="grid3">
            <div className="mini"><small>Series</small><b>{ex.sets}</b></div>
            <div className="mini"><small>Reps</small><b>{ex.reps_label || "—"}</b></div>
            <div className="mini"><small>Descanso</small><b>{mmss(ex.rest_seconds || 0)}</b></div>
          </div>
          {ex.notes && <div className="card tip"><Icon name="msg" size={16} />{ex.notes}</div>}
          {ex.exercise.instructions && <p>{ex.exercise.instructions}</p>}
          <small className="muted">{ex.exercise.muscle_label}{ex.exercise.secondary_muscles && ` · ${ex.exercise.secondary_muscles}`} · {ex.exercise.equipment_label}</small>
          {ex.exercise.video_url && <a className="btn block" href={ex.exercise.video_url} target="_blank" rel="noreferrer"><Icon name="play" size={18} />Ver video</a>}
          {ex.last && <small>Última vez: {ex.last.sets.map((s) => `${s.weight ? s.weight + "×" : ""}${s.reps ?? ""}`).join(" · ")}</small>}
          <Link className="btn primary block" to={`/progreso/ejercicio/${ex.exercise.id}`}>Ver mi progreso en este ejercicio</Link>
        </div>}
      </Sheet>
    </div>
  );
}
