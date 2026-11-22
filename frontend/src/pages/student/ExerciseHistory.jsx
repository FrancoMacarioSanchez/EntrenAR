import { useState } from "react";
import { useParams } from "react-router-dom";
import { LineChart } from "../../components/Charts";
import { Loader, Segmented } from "../../components/ui";
import { dateShort, num } from "../../lib/format";
import { useApi } from "../../lib/hooks";

const METRICS = [["best_e1rm", "1RM est."], ["max_weight", "Peso máx."], ["volume", "Volumen"], ["max_reps", "Reps máx."]];

export function HistoryView({ data }) {
  const bodyweight = data.history.every((h) => !h.max_weight);
  const [metric, setMetric] = useState(bodyweight ? "max_reps" : "best_e1rm");
  const pts = data.history.map((h) => ({ x: h.date, y: h[metric] || null }));
  const unit = metric === "max_reps" ? " reps" : " kg";
  return (
    <div className="stack">
      <div className="card">
        <Segmented value={metric} onChange={setMetric} options={bodyweight ? METRICS.slice(3) : METRICS} />
        <LineChart points={pts} unit={unit} yFormat={(v) => num(v, 1)} />
      </div>
      <div className="card list">{[...data.history].reverse().map((h) => (
        <div key={h.date} className="li"><span><b>{dateShort(h.date)}</b><br />
          <small className="muted">{h.sets.map((s) => `${s.weight ? s.weight + "×" : ""}${s.reps ?? ""}${s.to_failure ? "F" : ""}`).join(" · ")}</small></span>
          <span className="right">{h.best_e1rm ? <b>{h.best_e1rm} kg</b> : <b>{h.max_reps} reps</b>}<br /><small className="muted">vol. {num(h.volume, 0)}</small></span></div>))}</div>
    </div>
  );
}

export default function ExerciseHistory() {
  const { id } = useParams();
  const { data, loading } = useApi(`/me/exercises/${id}/history/`);
  if (loading && !data) return <Loader />;
  if (!data) return null;
  return (
    <div className="page-pad stack">
      <div><h1 className="title">{data.exercise.name}</h1><small className="muted">{data.exercise.muscle_label} · {data.exercise.equipment_label}</small></div>
      {data.records.length > 0 && <div className="h-scroll">{data.records.map((r) => (
        <div key={r.id} className="pr-card"><b>{r.label}</b><small>{r.kind_label}</small><small className="muted">{dateShort(r.achieved_at)}</small></div>))}</div>}
      <HistoryView data={data} />
    </div>
  );
}
