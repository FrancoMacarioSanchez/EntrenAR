import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Icon from "../../components/Icon";
import { Avatar, Empty, Loader, Segmented } from "../../components/ui";
import { ago } from "../../lib/format";
import { useApi } from "../../lib/hooks";

const FLAGS = { sin_rutina: ["Sin rutina", "bad"], rutina_vieja: ["Rutina vieja", "info"], no_entrena: ["No entrena", "warn"], cuota_vencida: ["Cuota vencida", "bad"] };

export default function Students() {
  const [sp, setSp] = useSearchParams();
  const [scope, setScope] = useState(sp.get("scope") || "mine");
  const [q, setQ] = useState("");
  const flag = sp.get("flag") || "";
  const { data, loading } = useApi(`/trainer/students/${scope === "mine" ? "?mine=1" : ""}`, { deps: [scope] });
  const list = (data?.results || []).filter((s) => (!flag || s.flags.includes(flag)) &&
    (!q || s.name.toLowerCase().includes(q.toLowerCase())));
  return (
    <div className="page-pad stack">
      <h1 className="title">Alumnos</h1>
      <Segmented value={scope} onChange={(v) => { setScope(v); setSp(v === "all" ? { scope: "all" } : {}); }} options={[["mine", "Mis alumnos"], ["all", "Todos"]]} />
      <div className="search-box"><Icon name="search" size={18} /><input className="input" placeholder="Buscar alumno" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <div className="chips-scroll">
        <button className={`chip ${!flag ? "on" : ""}`} onClick={() => setSp(scope === "all" ? { scope: "all" } : {})}>Todos</button>
        {Object.entries(FLAGS).map(([k, [l]]) => <button key={k} className={`chip ${flag === k ? "on" : ""}`} onClick={() => setSp({ ...(scope === "all" ? { scope: "all" } : {}), flag: k })}>{l}</button>)}
      </div>
      {loading && !data ? <Loader /> : !list.length ? <Empty icon="users" title="No hay alumnos acá" /> :
        <div className="card list">{list.map((s) => (
          <Link key={s.id} to={`/entrenador/alumnos/${s.id}`} className="li">
            <span className="row" style={{ gap: 12 }}><Avatar src={s.photo} initials={s.initials} size={42} />
              <span><b>{s.name}</b><br /><small className="muted">{s.goal_label} · último entreno {ago(s.last_session)}</small><br />
                <span className="row" style={{ gap: 4 }}>{s.flags.map((f) => <span key={f} className={`pill xs ${FLAGS[f][1]}`}>{FLAGS[f][0]}</span>)}</span></span></span>
            <Icon name="next" size={18} /></Link>))}</div>}
    </div>
  );
}
