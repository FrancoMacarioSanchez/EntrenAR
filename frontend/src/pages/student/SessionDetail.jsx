import { useParams } from "react-router-dom";
import Icon from "../../components/Icon";
import { Loader } from "../../components/ui";
import { dateLong, num } from "../../lib/format";
import { useApi } from "../../lib/hooks";

export function groupSets(sets) {
  const m = new Map();
  for (const s of sets) {
    if (!m.has(s.exercise)) m.set(s.exercise, { name: s.exercise_name, sets: [] });
    m.get(s.exercise).sets.push(s);
  }
  return [...m.values()];
}

export default function SessionDetail() {
  const { id } = useParams();
  const { data: s, loading } = useApi(`/me/sessions/${id}/`);
  if (loading && !s) return <Loader />;
  if (!s) return null;
  return (
    <div className="page-pad stack">
      <div><h1 className="title">{s.routine_day_name}</h1><small className="muted">{dateLong(s.date)} · {num(s.volume / 1000, 1)} t{s.duration_min ? ` · ${s.duration_min} min` : ""}</small></div>
      {s.trainer_feedback && <div className="card tip"><Icon name="msg" size={18} /><span><b>Tu entrenador:</b> {s.trainer_feedback}</span></div>}
      {groupSets(s.sets).map((g) => (
        <div key={g.name} className="card"><h3>{g.name}</h3>
          {g.sets.map((x) => <div key={x.id} className="li"><span>Serie {x.set_number}</span>
            <b>{x.weight != null ? `${x.weight} kg × ` : ""}{x.reps ?? ""}{x.duration_seconds ? `${x.duration_seconds}s` : ""}{x.to_failure ? " (fallo)" : ""}</b></div>)}</div>
      ))}
      {s.notes && <div className="card"><small className="muted">Tus notas</small><p>{s.notes}</p></div>}
    </div>
  );
}
