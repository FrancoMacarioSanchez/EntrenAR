import { Link } from "react-router-dom";
import Icon from "../../components/Icon";
import { Empty, Loader } from "../../components/ui";
import { dateLong } from "../../lib/format";
import { useApi } from "../../lib/hooks";

export default function MyClasses() {
  const { data, loading } = useApi("/trainer/classes/?days=14");
  if (loading && !data) return <Loader />;
  const items = data?.results || [];
  const byDate = items.reduce((acc, c) => { (acc[c.date] = acc[c.date] || []).push(c); return acc; }, {});
  return (
    <div className="page-pad stack">
      <h1 className="title">Mis clases</h1>
      {!items.length ? <Empty icon="cal" title="No tenés clases asignadas">El gimnasio te asigna las clases desde el panel (Administración → Horarios de clases).</Empty> :
        Object.entries(byDate).map(([d, list]) => (
          <section key={d}>
            <div className="sec-head"><h3 style={{ textTransform: "capitalize" }}>{dateLong(d)}</h3></div>
            {list.map((c) => (
              <Link key={c.id + d} to={`/entrenador/clases/${c.id}/${d}`} className={`card class-card ${c.cancelled ? "suspended" : ""}`} style={{ borderLeftColor: c.color, marginBottom: 10 }}>
                <div><b className="time">{c.time}</b><h3>{c.name}</h3>
                  <small className="muted">{c.room && `${c.room} · `}{c.duration} min</small>
                  {c.cancelled ? <div><span className="pill bad xs">Suspendida{c.cancel_reason ? ` · ${c.cancel_reason}` : ""}</span></div> : <>
                    <div className="track"><span style={{ width: `${Math.min(100, (c.booked / c.capacity) * 100)}%`, background: c.color }} /></div>
                    <small>{c.booked}/{c.capacity} anotados{c.waitlist ? ` · ${c.waitlist} en espera` : ""}{c.attended ? ` · ${c.attended} presentes` : ""}</small></>}
                </div>
                <Icon name="next" />
              </Link>
            ))}
          </section>
        ))}
    </div>
  );
}
