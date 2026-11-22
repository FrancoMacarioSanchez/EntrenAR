import { Link, useNavigate } from "react-router-dom";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { Empty, Loader, Segmented } from "../../components/ui";
import { del, post } from "../../lib/api";
import { dateShort } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { useState } from "react";

export default function Routines() {
  const [tab, setTab] = useState("templates");
  const { data, loading, reload } = useApi(tab === "templates" ? "/routines/?templates=1" : "/routines/");
  const nav = useNavigate();
  const toast = useToast();
  const list = (data?.results || []).filter((r) => (tab === "templates" ? r.is_template : !r.is_template));
  return (
    <div className="page-pad stack">
      <div className="row between"><h1 className="title">Rutinas</h1><div className="row"><Link className="btn" to="/entrenador/ejercicios"><Icon name="dumbbell" size={18} />Ejercicios</Link><Link className="btn primary" to="/entrenador/rutinas/nueva"><Icon name="plus" size={18} />Nueva</Link></div></div>
      <Segmented value={tab} onChange={setTab} options={[["templates", "Plantillas"], ["mine", "Asignadas por mí"]]} />
      {loading && !data ? <Loader /> : !list.length ? <Empty icon="list" title={tab === "templates" ? "Sin plantillas" : "Sin rutinas"}>
        Armá una plantilla una vez y asignala a muchos alumnos en un toque.</Empty> :
        list.map((r) => (
          <div key={r.id} className="card">
            <div className="sec-head"><div><h3>{r.name}</h3><small className="muted">{r.member_name ? `${r.member_name} · ` : ""}{r.days.length} días · {r.goal || "—"} · {dateShort(r.updated_at)}</small></div>
              {r.is_active && !r.is_template && <span className="pill ok xs">Activa</span>}</div>
            <small className="muted">{r.days.map((d) => d.name).join(" · ")}</small>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn sm" onClick={() => nav(`/entrenador/rutinas/${r.id}`)}><Icon name="edit" size={16} />Editar</button>
              {r.is_template && <button className="btn sm" onClick={() => nav(`/entrenador/rutinas/nueva?template=${r.id}`)}><Icon name="copy" size={16} />Usar para un alumno</button>}
              {!r.is_template && <button className="btn sm" onClick={async () => { await post(`/routines/${r.id}/duplicate/`, { as_template: true, name: `${r.name} (plantilla)` }); toast("Guardada como plantilla", "success"); }}>Guardar como plantilla</button>}
              <button className="btn sm ghost danger-text" onClick={async () => { if (confirm("¿Eliminar/archivar la rutina?")) { await del(`/routines/${r.id}/`); reload(); } }}><Icon name="trash" size={16} /></button>
            </div>
          </div>))}
    </div>
  );
}
