import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { post } from "../lib/api";
import { useAuth } from "../state/auth";
import { useToast } from "../components/Toast";

export default function ChangePassword({ forced }) {
  const { reload, logout } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const [f, setF] = useState({ old_password: "", new_password: "", confirm: "" });
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    if (f.new_password !== f.confirm) return setErr("Las contraseñas no coinciden.");
    try {
      await post("/me/password/", { old_password: f.old_password, new_password: f.new_password });
      toast("Contraseña actualizada", "success");
      await reload();
      nav("/");
    } catch (e2) { setErr(e2.message); }
  };
  return (
    <div className={forced ? "login-form standalone" : "page-pad"}>
      <form className="card stack" onSubmit={submit}>
        <h2>{forced ? "Elegí tu contraseña" : "Cambiar contraseña"}</h2>
        {forced && <p className="muted">Por seguridad, cambiá la contraseña inicial antes de empezar.</p>}
        {["old_password", "new_password", "confirm"].map((k, i) => (
          <label className="field" key={k}><span>{["Contraseña actual", "Nueva contraseña", "Repetir nueva contraseña"][i]}</span>
            <input className="input lg" type="password" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} required minLength={k === "old_password" ? 1 : 6} /></label>
        ))}
        {err && <div className="alert bad">{err}</div>}
        <button className="btn primary lg block">Guardar</button>
        {forced && <button type="button" className="btn ghost block" onClick={logout}>Salir</button>}
      </form>
    </div>
  );
}
