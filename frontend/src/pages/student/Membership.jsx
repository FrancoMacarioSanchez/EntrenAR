import { useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../../components/Icon";
import QR from "../../components/QR";
import { useToast } from "../../components/Toast";
import { Loader } from "../../components/ui";
import { post } from "../../lib/api";
import { dateShort, money } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { useAuth } from "../../state/auth";

const ST = {
  active: ["Al día", "ok"], expiring: ["Vence pronto", "warn"], grace: ["Vencida · en tolerancia", "warn"],
  expired: ["Vencida", "bad"], frozen: ["Congelada", "info"], none: ["Sin plan", "bad"],
};

export default function Membership() {
  const { gym, me } = useAuth();
  const toast = useToast();
  const { data, loading } = useApi("/me/membership/");
  const [paying, setPaying] = useState(null);
  if (loading && !data) return <Loader />;
  if (!data) return null;
  const [label, kind] = ST[data.state] || ST.none;
  const m = data.membership;
  const pay = async (id) => {
    setPaying(id);
    try { const r = await post(`/me/charges/${id}/pay/`); window.location.href = r.url; }
    catch (e) { toast(e.message, "error"); setPaying(null); }
  };
  return (
    <div className="page-pad stack">
      <div className={`card qr-card ${kind}`}>
        <small>Mostrá este código en recepción</small>
        <QR value={data.access_code} size={230} />
        <b className="mono">{data.access_code}</b>
        <h2>{me.member.name}</h2>
        <span className={`pill ${kind}`}>{label}</span>
        <small className="muted">Subí el brillo de la pantalla para escanear más rápido.</small>
      </div>
      {gym?.self_checkin_enabled && <Link className="btn primary lg block" to="/escanear"><Icon name="scan" size={20} />Escanear el QR de la entrada</Link>}
      {m && <div className="card list">
        <div className="li"><span>Plan</span><b>{m.plan}</b></div>
        <div className="li"><span>Vigencia</span><b>{dateShort(m.start_date)} → {dateShort(m.end_date)}</b></div>
        <div className="li"><span>Días restantes</span><b>{Math.max(m.remaining_days, 0)}</b></div>
        {m.visits_left != null && <div className="li"><span>Ingresos disponibles</span><b>{m.visits_left}</b></div>}
        <div className="li"><span>Renovación automática</span><b>{m.auto_renew ? "Sí" : "No"}</b></div>
        <div className="li"><span>Ingresos este mes</span><b>{data.checkins_month}</b></div>
      </div>}
      {data.charges.length > 0 && <section className="card">
        <div className="sec-head"><h3>Pendiente de pago</h3><b className="c-bad">{money(data.debt)}</b></div>
        {data.charges.map((c) => (
          <div key={c.id} className="li"><span><b>{c.concept}</b><br /><small className={c.overdue ? "c-bad" : "muted"}>Vence {dateShort(c.due_date)}</small></span>
            <span className="right"><b>{money(c.balance)}</b><br />
              {gym?.mp_enabled && <button className="btn sm primary" disabled={paying === c.id} onClick={() => pay(c.id)}>{paying === c.id ? "…" : "Pagar"}</button>}</span></div>))}
        {!gym?.mp_enabled && <small className="muted">Podés abonar en recepción.</small>}
      </section>}
      {data.promotions?.length > 0 && <section>
        <div className="sec-head"><h3>🎁 Promociones vigentes</h3></div>
        <div className="h-scroll">{data.promotions.map((p) => <PromoCard key={p.id} p={p} />)}</div>
        <small className="muted">Pedila en recepción al renovar.</small>
      </section>}
      {data.notes.length > 0 && <section className="card"><div className="sec-head"><h3>Mensajes del gimnasio</h3></div>
        {data.notes.map((n, i) => <div key={i} className="card tip"><Icon name="msg" size={16} /><span>{n.text}<br /><small className="muted">{n.author} · {dateShort(n.date)}</small></span></div>)}</section>}
      <section className="card"><div className="sec-head"><h3>Pagos</h3></div>
        {data.payments.length ? data.payments.map((p) => (
          <div key={p.id} className="li"><span><b>{p.concept || "Pago"}</b><br /><small className="muted">{dateShort(p.date)} · {p.method}{p.invoice_number ? ` · Fact. ${p.invoice_number}` : ""}</small></span><b>{money(p.amount)}</b></div>))
          : <p className="muted">Sin pagos registrados.</p>}</section>
    </div>
  );
}

export function PromoCard({ p }) {
  return (
    <div className="promo-card" style={{ background: `linear-gradient(135deg, ${p.color}, #111)` }}>
      <b className="promo-big">{p.summary}</b>
      <b>{p.name}</b>
      {p.description && <small>{p.description}</small>}
      <small className="promo-meta">{p.plans.length ? p.plans.join(", ") : "Todos los planes"}{p.ends_on ? ` · hasta ${dateShort(p.ends_on)}` : ""}{p.code ? ` · código ${p.code}` : ""}</small>
    </div>
  );
}
