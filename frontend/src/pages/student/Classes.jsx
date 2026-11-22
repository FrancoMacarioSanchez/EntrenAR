import { useState } from "react";
import { useToast } from "../../components/Toast";
import { Empty, Loader } from "../../components/ui";
import { post } from "../../lib/api";
import { dayName } from "../../lib/format";
import { useApi } from "../../lib/hooks";

export default function Classes() {
  const toast = useToast();
  const { data, loading, reload } = useApi("/classes/");
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(null);
  if (loading && !data) return <Loader />;
  const days = data?.days || [];
  const day = days[i];
  const act = async (fn, id) => {
    setBusy(id);
    try { await fn(); await reload(); } catch (e) { toast(e.message, "error"); } finally { setBusy(null); }
  };
  return (
    <div className="page-pad stack">
      <h1 className="title">Clases</h1>
      <div className="chips-scroll days">{days.map((d, j) => (
        <button key={d.date} className={`chip day ${i === j ? "on" : ""}`} onClick={() => setI(j)}>
          <span>{dayName(d.date)}</span>{d.items.some((x) => x.my_booking) && <i className="dot" />}</button>))}</div>
      {!day?.items.length ? <Empty icon="cal" title="No hay clases este día" /> : day.items.map((c) => {
        const full = c.booked >= c.capacity;
        const mine = c.my_booking;
        return (
          <div key={c.id} className="card class-card" style={{ borderLeftColor: c.color }}>
            <div><b className="time">{c.time}</b><h3>{c.name}</h3>
              <small className="muted">{c.trainer}{c.room && ` · ${c.room}`} · {c.duration} min</small>
              <div className="track"><span style={{ width: `${Math.min(100, (c.booked / c.capacity) * 100)}%`, background: c.color }} /></div>
              <small>{c.booked}/{c.capacity} lugares</small></div>
            {c.cancelled ? <span className="pill bad">Suspendida{c.cancel_reason ? ` · ${c.cancel_reason}` : ""}</span>
              : mine ? <div className="right"><span className={`pill ${mine.status === "waitlist" ? "warn" : "ok"}`}>{mine.status === "waitlist" ? "En espera" : "Reservada"}</span>
              <button className="btn sm ghost" disabled={busy === c.id} onClick={() => act(() => post(`/bookings/${mine.id}/cancel/`), c.id)}>Cancelar</button></div>
              : c.opens_in_hours > 0 ? <small className="muted">Abre en {c.opens_in_hours} h</small>
              : <button className="btn sm primary" disabled={busy === c.id} onClick={() => act(() => post(`/classes/${c.id}/book/`, { date: day.date }).then((r) => toast(r.status === "waitlist" ? "Quedaste en lista de espera" : "¡Reservado!", "success")), c.id)}>
                {full ? "Lista de espera" : "Reservar"}</button>}
          </div>
        );
      })}
    </div>
  );
}
