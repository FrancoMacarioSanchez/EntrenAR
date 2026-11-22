import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import { useToast } from "../components/Toast";
import { Avatar } from "../components/ui";
import { api } from "../lib/api";
import { enablePush, pushEnabled, pushSupported } from "../lib/push";
import { useAuth } from "../state/auth";

export default function Profile() {
  const { me, gym, logout, reload } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const file = useRef();
  const [push, setPush] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("entrenar.theme") || "auto");
  useEffect(() => { pushEnabled().then(setPush); }, []);
  useEffect(() => {
    if (theme === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    localStorage.setItem("entrenar.theme", theme);
  }, [theme]);
  const u = me.user, m = me.member;

  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const form = new FormData(); form.append("photo", f);
    try { await api("/me/photo/", { method: "POST", form }); await reload(); toast("Foto actualizada", "success"); }
    catch (err) { toast(err.message, "error"); }
  };
  const doPush = async () => {
    try { await enablePush(gym?.vapid_public_key); setPush(true); toast("¡Notificaciones activadas!", "success"); }
    catch (e) { toast(e.message, "error", 6000); }
  };

  return (
    <div className="page-pad stack">
      <div className="card center profile-head">
        <button className="avatar-edit" onClick={() => file.current.click()}>
          <Avatar src={m?.photo || u.avatar} initials={(u.first_name?.[0] || "") + (u.last_name?.[0] || "")} size={92} />
          <span><Icon name="camera" size={16} /></span></button>
        <input type="file" accept="image/*" ref={file} hidden onChange={upload} />
        <h2>{u.name}</h2>
        <small className="muted">@{u.username} · {m ? m.goal_label : "Entrenador"}</small>
      </div>
      {m && <div className="card list">
        <div className="li"><span>DNI</span><b>{m.dni || "—"}</b></div>
        <div className="li"><span>Entrenador</span><b>{m.trainer || "Sin asignar"}</b></div>
        <div className="li"><span>Altura</span><b>{m.height_cm ? `${m.height_cm} cm` : "—"}</b></div>
        <div className="li"><span>Apto físico</span><b className={m.medical_ok ? "ok" : "warn"}>{m.medical_ok ? "Vigente" : "Pendiente"}</b></div>
        <div className="li"><span>Socio desde</span><b>{m.joined_at}</b></div>
      </div>}
      <div className="card list">
        {pushSupported() && <button className="li" onClick={doPush} disabled={push}><span><Icon name="bell" size={18} /> Notificaciones</span><b>{push ? "Activadas" : "Activar"}</b></button>}
        <div className="li"><span><Icon name="star" size={18} /> Tema</span>
          <select className="input" value={theme} onChange={(e) => setTheme(e.target.value)} style={{ width: "auto" }}>
            <option value="auto">Automático</option><option value="light">Claro</option><option value="dark">Oscuro</option></select></div>
        <button className="li" onClick={() => nav("/password")}><span><Icon name="edit" size={18} /> Cambiar contraseña</span><Icon name="next" size={18} /></button>
        {m && <button className="li" onClick={() => nav("/cuerpo?avatar=1")}><span><Icon name="body" size={18} /> Personalizar mi avatar</span><Icon name="next" size={18} /></button>}
        {m && <button className="li" onClick={() => nav("/clases")}><span><Icon name="cal" size={18} /> Clases y reservas</span><Icon name="next" size={18} /></button>}
        {m && <button className="li" onClick={() => nav("/rutina")}><span><Icon name="list" size={18} /> Mi rutina completa</span><Icon name="next" size={18} /></button>}
      </div>
      {gym && <div className="card list">
        <div className="li"><span>{gym.name}</span><b>{gym.opening_hours}</b></div>
        {gym.address && <div className="li"><span>Dirección</span><b>{gym.address}</b></div>}
        {gym.whatsapp && <a className="li" href={`https://wa.me/${gym.whatsapp.replace(/\D/g, "")}`} target="_blank" rel="noreferrer"><span><Icon name="msg" size={18} /> Escribir al gimnasio</span><Icon name="next" size={18} /></a>}
      </div>}
      <button className="btn danger block" onClick={async () => { await logout(); nav("/login"); }}><Icon name="logout" size={18} />Cerrar sesión</button>
      <small className="muted center">EntrenAR · CoreX</small>
    </div>
  );
}
