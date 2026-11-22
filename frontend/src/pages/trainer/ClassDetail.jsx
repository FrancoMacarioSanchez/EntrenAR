import { useState } from "react";
import { useParams } from "react-router-dom";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { Avatar, Empty, Field, Loader, Sheet, Stepper } from "../../components/ui";
import { api } from "../../lib/api";
import { dateLong } from "../../lib/format";
import { useApi } from "../../lib/hooks";

const ST = { booked: ["Anotado", ""], attended: ["Presente", "ok"], no_show: ["Ausente", "bad"], waitlist: ["En espera", "warn"], cancelled: ["Cancelado", "muted"] };

export default function ClassDetail() {
  const { id, date } = useParams();
  const toast = useToast();
  const { data, loading, setData } = useApi(`/trainer/classes/${id}/${date}/`, { cache: false });
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [suspend, setSuspend] = useState(null);
  const [busy, setBusy] = useState(false);

  const act = async (body, msg) => {
    setBusy(true);
    try { setData(await api(`/trainer/classes/${id}/${date}/`, { method: "POST", body })); if (msg) toast(msg, "success"); }
    catch (e) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const saveEdit = async () => {
    try {
      await api(`/trainer/classes/${id}/`, { method: "PATCH", body: editing });
      setData({ ...data, ...editing }); setEditing(null); toast("Clase actualizada", "success");
    } catch (e) { toast(e.message, "error"); }
  };

  if (loading && !data) return <Loader />;
  if (!data) return null;
  const active = data.bookings.filter((b) => b.status !== "cancelled");
  const present = active.filter((b) => b.status === "attended").length;
  return (
    <div className="page-pad stack">
      <div className="class-hero" style={{ background: `linear-gradient(135deg, ${data.color}, #111)` }}>
        <small style={{ textTransform: "capitalize" }}>{dateLong(data.date)} · {data.time}</small>
        <h1>{data.name}</h1>
        <p>{data.room && `${data.room} · `}{data.duration} min · cupo {data.capacity}</p>
        <div className="row"><span className="pill">{active.filter((b) => b.status !== "waitlist").length}/{data.capacity} anotados</span><span className="pill">{present} presentes</span></div>
      </div>
      {data.cancelled && <div className="card tip warn"><Icon name="info" size={18} /><span><b>Clase suspendida.</b> {data.cancel_reason}<br />
        <button className="btn sm" style={{ marginTop: 8 }} onClick={() => act({ action: "restore" }, "Clase habilitada")}>Volver a habilitarla</button></span></div>}

      <div className="row">
        <button className="btn primary block" disabled={busy || data.cancelled} onClick={() => setAdding(true)}><Icon name="plus" size={18} />Anotar alumno</button>
        <button className="btn block" disabled={busy || data.cancelled || !active.some((b) => b.status === "booked")} onClick={() => act({ action: "all_attended" }, "Todos presentes")}><Icon name="check" size={18} />Todos presentes</button>
      </div>

      {!active.length ? <Empty icon="users" title="Nadie anotado todavía" /> : <div className="card list">
        {active.map((b) => (
          <div key={b.id} className="li">
            <span className="row" style={{ gap: 10 }}><Avatar src={b.photo} initials={b.initials} size={38} />
              <span><b>{b.name}</b><br /><span className={`pill xs ${ST[b.status][1]}`}>{ST[b.status][0]}</span></span></span>
            <span className="row" style={{ gap: 4 }}>
              <button className={`att ${b.status === "attended" ? "on ok" : ""}`} disabled={busy} title="Presente" onClick={() => act({ action: "attended", booking: b.id })}><Icon name="check" size={18} stroke={3} /></button>
              <button className={`att ${b.status === "no_show" ? "on bad" : ""}`} disabled={busy} title="Ausente" onClick={() => act({ action: "no_show", booking: b.id })}><Icon name="x" size={18} stroke={3} /></button>
              <button className="att" disabled={busy} title="Quitar de la clase" onClick={() => confirm(`¿Quitar a ${b.name} de la clase?`) && act({ action: "remove", booking: b.id }, "Quitado")}><Icon name="trash" size={16} /></button>
            </span>
          </div>))}
      </div>}

      <div className="row">
        <button className="btn block" onClick={() => setEditing({ capacity: data.capacity, room: data.room, duration_min: data.duration, description: data.description })}><Icon name="edit" size={18} />Editar clase</button>
        {!data.cancelled && <button className="btn block danger" onClick={() => setSuspend("")}>Suspender este día</button>}
      </div>

      <MemberPicker open={adding} onClose={() => setAdding(false)} exclude={active.map((b) => b.member)}
        onPick={(m) => { setAdding(false); act({ action: "add", member: m.id }, `${m.name} anotado/a`); }} />

      <Sheet open={!!editing} onClose={() => setEditing(null)} title="Editar clase">
        {editing && <div className="stack">
          <Field label="Cupo"><Stepper value={editing.capacity} onChange={(v) => setEditing({ ...editing, capacity: v })} inputMode="numeric" min={1} /></Field>
          <Field label="Duración (min)"><Stepper value={editing.duration_min} onChange={(v) => setEditing({ ...editing, duration_min: v })} step={5} inputMode="numeric" /></Field>
          <Field label="Sala"><input className="input" value={editing.room || ""} onChange={(e) => setEditing({ ...editing, room: e.target.value })} /></Field>
          <Field label="Descripción"><input className="input" value={editing.description || ""} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></Field>
          <small className="muted">El día y el horario los cambia el gimnasio desde el panel. Los cambios aplican a todas las fechas.</small>
          <button className="btn primary block" onClick={saveEdit}>Guardar</button>
        </div>}
      </Sheet>
      <Sheet open={suspend !== null} onClose={() => setSuspend(null)} title="Suspender la clase de este día">
        <div className="stack">
          <p className="muted">Les avisamos a los anotados con una notificación.</p>
          <input className="input" placeholder="Motivo (opcional)" value={suspend || ""} onChange={(e) => setSuspend(e.target.value)} />
          <button className="btn danger block" onClick={() => { act({ action: "suspend", reason: suspend }, "Clase suspendida"); setSuspend(null); }}>Suspender</button>
        </div>
      </Sheet>
    </div>
  );
}

function MemberPicker({ open, onClose, onPick, exclude }) {
  const { data } = useApi(open ? "/trainer/students/" : null);
  const [q, setQ] = useState("");
  const list = (data?.results || []).filter((s) => !exclude.includes(s.id) && (!q || s.name.toLowerCase().includes(q.toLowerCase())));
  return (
    <Sheet open={open} onClose={onClose} title="Anotar alumno" tall>
      <div className="search-box"><Icon name="search" size={18} /><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar" autoFocus /></div>
      {!data ? <Loader /> : <div className="list">{list.map((s) => (
        <button key={s.id} className="li" onClick={() => onPick(s)}><span className="row" style={{ gap: 10 }}><Avatar src={s.photo} initials={s.initials} size={34} /><b>{s.name}</b></span><Icon name="plus" size={18} /></button>))}</div>}
    </Sheet>
  );
}
