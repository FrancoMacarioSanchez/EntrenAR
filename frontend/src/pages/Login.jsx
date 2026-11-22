import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import { useAuth } from "../state/auth";

export default function Login() {
  const { me, login, gym } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = loc.state?.from || "/";
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  if (me) return <Navigate to={from} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await login(u.trim(), p); nav(from, { replace: true }); }
    catch (e2) { setErr(e2.message); }
    finally { setBusy(false); }
  };
  return (
    <div className="login">
      <div className="login-art">
        <div className="blob b1" /><div className="blob b2" />
        {gym?.logo ? <img src={gym.logo} alt="" className="login-logo" /> : <div className="login-logo letter">{gym?.name?.[0] || "E"}</div>}
        <h1>{gym?.name || "EntrenAR"}</h1>
        <p>{from.startsWith("/ingreso") ? "Ingresá con tu usuario para registrar tu entrada al gimnasio." : "Tu entrenamiento, tus récords y tu progreso en un solo lugar."}</p>
      </div>
      <form className="login-form" onSubmit={submit}>
        <label className="field"><span>Usuario, email o DNI</span>
          <input className="input lg" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" autoCapitalize="none" required /></label>
        <label className="field"><span>Contraseña</span>
          <div className="pass"><input className="input lg" type={show ? "text" : "password"} value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required />
            <button type="button" className="icon-btn" onClick={() => setShow(!show)}><Icon name={show ? "x" : "info"} size={18} /></button></div></label>
        {err && <div className="alert bad">{err}</div>}
        <button className="btn primary lg block" disabled={busy}>{busy ? "Ingresando…" : "Ingresar"}</button>
        <small className="muted center">¿Primera vez? Tu usuario y contraseña inicial es tu DNI. Si no funciona, pedilo en recepción.</small>
      </form>
    </div>
  );
}
