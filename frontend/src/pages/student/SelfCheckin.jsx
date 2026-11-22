import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Icon from "../../components/Icon";
import { Confetti } from "../../components/ui";
import { post } from "../../lib/api";
import { dateShort, money } from "../../lib/format";
import { useAuth } from "../../state/auth";

function getPosition(timeout = 8000) {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }), () => resolve(null),
      { enableHighAccuracy: true, timeout, maximumAge: 60000 });
  });
}

// Se abre al escanear el QR del gimnasio: /app/ingreso?k=...
export default function SelfCheckin() {
  const [sp] = useSearchParams();
  const k = sp.get("k");
  const { gym } = useAuth();
  const nav = useNavigate();
  const [st, setSt] = useState({ phase: "loading" });
  const done = useRef(false);

  const run = async (withLocation) => {
    setSt({ phase: withLocation ? "locating" : "loading" });
    const body = { k };
    if (withLocation) {
      const pos = await getPosition();
      if (pos) Object.assign(body, pos);
    }
    try {
      const r = await post("/me/checkin/", body);
      setSt({ phase: "done", r });
      navigator.vibrate?.(r.allowed ? [60, 40, 120] : [300]);
    } catch (e) {
      if (e.data?.code === "location_required" && !withLocation) return run(true);
      setSt({ phase: "error", msg: e.message, code: e.data?.code });
    }
  };

  useEffect(() => {
    if (done.current) return;
    done.current = true;
    if (!k) { setSt({ phase: "error", msg: "Falta el código. Escaneá el QR del gimnasio." }); return; }
    run(!!gym?.checkin_require_location);
  }, [k]); // eslint-disable-line react-hooks/exhaustive-deps

  const r = st.r;
  return (
    <div className="page-pad">
      <Confetti show={st.phase === "done" && r.allowed && !r.already} />
      {(st.phase === "loading" || st.phase === "locating") && (
        <div className="checkin-res wait"><span className="spinner big" />
          <h2>{st.phase === "locating" ? "Confirmando que estás en el gimnasio…" : "Registrando tu ingreso…"}</h2></div>
      )}
      {st.phase === "done" && (
        <div className={`checkin-res ${r.allowed ? "ok" : "bad"}`}>
          <div className="big-ico"><Icon name={r.allowed ? "check" : "x"} size={56} stroke={3} /></div>
          <h1>{r.allowed ? (r.already ? "Ya estás adentro" : `¡Bienvenido/a, ${r.name}!`) : "No pudimos registrar tu ingreso"}</h1>
          <p>{r.allowed ? (r.already ? "Tu ingreso de hoy ya estaba registrado." : r.reason) : `${r.reason}. Pasá por recepción.`}</p>
          <div className="row" style={{ justifyContent: "center", flexWrap: "wrap" }}>
            {r.plan && <span className="pill">{r.plan} · vence {dateShort(r.end_date)}</span>}
            {r.visits_left != null && <span className="pill info">Te quedan {r.visits_left} ingresos</span>}
            {r.debt > 0 && <span className="pill bad">Saldo {money(r.debt)}</span>}
          </div>
          <div className="stack" style={{ width: "100%", marginTop: 18 }}>
            {r.allowed ? <button className="btn primary lg block" onClick={() => nav("/entrenar")}><Icon name="play" size={18} />Empezar a entrenar</button>
              : <Link className="btn primary lg block" to="/membresia">Ver mi membresía</Link>}
            <Link className="btn block" to="/">Ir al inicio</Link>
          </div>
        </div>
      )}
      {st.phase === "error" && (
        <div className="checkin-res bad">
          <div className="big-ico"><Icon name="info" size={52} /></div>
          <h2>{st.msg}</h2>
          {st.code === "location_required" && <p className="muted">Permití el acceso a la ubicación en tu navegador y probá de nuevo.</p>}
          <div className="stack" style={{ width: "100%", marginTop: 18 }}>
            {k && <button className="btn primary lg block" onClick={() => run(true)}>Reintentar</button>}
            <Link className="btn block" to="/escanear">Escanear de nuevo</Link>
            <Link className="btn ghost block" to="/membresia">Mostrar mi QR en recepción</Link>
          </div>
        </div>
      )}
    </div>
  );
}
