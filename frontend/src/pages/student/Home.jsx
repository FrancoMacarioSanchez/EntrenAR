import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Icon from "../../components/Icon";
import InstallPrompt from "../../components/InstallPrompt";
import { Ring } from "../../components/ui";
import { kv } from "../../lib/db";
import { ago, dateShort, greeting, num } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { useAuth } from "../../state/auth";
import { PromoCard } from "./Membership";

const STATE = {
  active: ["Cuota al día", "ok"], expiring: ["Vence pronto", "warn"], grace: ["Cuota vencida", "warn"],
  expired: ["Cuota vencida", "bad"], frozen: ["Congelada", "info"], none: ["Sin plan activo", "bad"],
};

export default function Home() {
  const { me, gym } = useAuth();
  const nav = useNavigate();
  const m = me.member;
  const routine = useApi("/me/routine/");
  const progress = useApi("/me/progress/");
  const board = useApi("/leaderboard/");
  const promos = useApi("/promotions/");
  const food = useApi(gym?.nutrition === false ? null : `/me/nutrition/day/`);
  const [current, setCurrent] = useState(null);
  useEffect(() => { kv.get("workout:current").then(setCurrent).catch(() => {}); }, []);

  const r = routine.data?.routine;
  const nextDay = r?.days.find((d) => d.id === r.next_day) || r?.days[0];
  const p = progress.data;
  const [stLabel, stKind] = STATE[m.membership_state] || STATE.none;
  const goalSessions = 12;

  return (
    <div className="page-pad stack">
      <section className="hello">
        <div>
          <small className="muted">{greeting()}</small>
          <h1>{m.first_name} 👋</h1>
        </div>
        <Link to="/membresia" className={`pill ${stKind}`}><Icon name="qr" size={15} />{stLabel}{m.membership_end && ` · ${dateShort(m.membership_end)}`}</Link>
      </section>

      {current && (
        <button className="card resume" onClick={() => nav(`/entrenar/${current.routine_day || ""}`)}>
          <span className="ico-bubble pulse"><Icon name="play" size={18} /></span>
          <span><b>Tenés un entrenamiento en curso</b><br /><small>{current.day_name} · empezaste {ago(current.started_at)}</small></span>
          <Icon name="next" />
        </button>
      )}

      <div className="hero-card" onClick={() => nav(nextDay ? `/entrenar/${nextDay.id}` : "/entrenar/libre")}>
        <div className="hero-glow" />
        {r ? <>
          <small>Hoy te toca</small>
          <h2>{nextDay?.name}</h2>
          <p>{nextDay?.exercises.length} ejercicios · {r.name}</p>
          <div className="row">
            <span className="btn light"><Icon name="play" size={18} />Empezar</span>
            <Link to="/rutina" className="btn ghost-light" onClick={(e) => e.stopPropagation()}>Ver rutina</Link>
          </div>
        </> : <>
          <small>Todavía no tenés rutina</small>
          <h2>Entrenamiento libre</h2>
          <p>Tu entrenador te la va a cargar. Mientras tanto podés registrar lo que hagas.</p>
          <span className="btn light"><Icon name="play" size={18} />Empezar libre</span>
        </>}
      </div>

      {food.data && (
        <Link to="/nutricion" className="card nutri-mini">
          <span className="ico-bubble"><Icon name="food" size={18} /></span>
          {food.data.targets ? <span className="grow"><b>Comidas de hoy</b><br />
            <small className="muted">{Math.round(food.data.totals.kcal)} de {food.data.targets.kcal} kcal · {Math.round(food.data.totals.protein)} de {food.data.targets.protein} g de proteína</small>
            <span className="mini-track"><i style={{ width: `${Math.min(100, (food.data.totals.kcal / food.data.targets.kcal) * 100)}%` }} /></span></span>
            : <span className="grow"><b>Registrá lo que comés</b><br /><small className="muted">Sacale una foto al plato y calculamos calorías y macros.</small></span>}
          <Icon name="next" />
        </Link>
      )}

      {gym?.welcome_message && !p?.sessions_total && <div className="card tip"><Icon name="info" size={18} />{gym.welcome_message}</div>}

      <div className="card stats-row">
        <Ring value={p?.sessions_month || 0} max={goalSessions} size={108} label={p?.sessions_month ?? "–"} sub="este mes" />
        <div className="stats-col">
          <div><Icon name="fire" size={18} className="c-fire" /><b>{p?.week_streak ?? "–"}</b><small>semanas seguidas</small></div>
          <div><Icon name="trophy" size={18} className="c-gold" /><b>{p?.records?.length ?? "–"}</b><small>récords</small></div>
          <div><Icon name="dumbbell" size={18} /><b>{p ? num(p.total_volume / 1000, 1) : "–"} t</b><small>levantadas</small></div>
        </div>
      </div>

      <InstallPrompt />

      <div className="quick">
        <Link to="/membresia" className="q"><Icon name="qr" /><span>Mi QR</span></Link>
        <Link to="/clases" className="q"><Icon name="cal" /><span>Clases</span></Link>
        <Link to="/cuerpo" className="q"><Icon name="body" /><span>Medidas</span></Link>
        <Link to="/escanear" className="q"><Icon name="scan" /><span>Ingresar</span></Link>
      </div>

      {promos.data?.results?.length > 0 && <section>
        <div className="sec-head"><h3>🎁 Promociones</h3><Link to="/membresia">Ver</Link></div>
        <div className="h-scroll">{promos.data.results.map((x) => <PromoCard key={x.id} p={x} />)}</div>
      </section>}

      {p?.records?.length > 0 && <section>
        <div className="sec-head"><h3>Últimos récords</h3><Link to="/progreso">Ver todo</Link></div>
        <div className="h-scroll">{p.records.slice(0, 8).map((x) => (
          <Link key={x.id} to={`/progreso/ejercicio/${x.exercise}`} className="pr-card">
            <Icon name="trophy" className="c-gold" /><b>{x.exercise_name}</b><small>{x.label}</small><small className="muted">{ago(x.achieved_at)}</small>
          </Link>))}</div>
      </section>}

      {p?.achievements?.length > 0 && <section>
        <div className="sec-head"><h3>Logros</h3></div>
        <div className="badges">{p.achievements.map((a) => <span key={a.code} className="ach" title={a.description}><i>{a.icon}</i>{a.title}</span>)}</div>
      </section>}

      {board.data?.results?.length > 0 && <section className="card">
        <div className="sec-head"><h3>🔥 Ranking de constancia del mes</h3></div>
        {board.data.results.slice(0, 5).map((x, i) => (
          <div key={i} className={`rank ${x.me ? "me" : ""}`}><span className="pos">{i + 1}</span><span>{x.name}</span><b>{x.sessions} entrenamientos</b></div>))}
      </section>}
    </div>
  );
}
