import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useOnline } from "../lib/hooks";
import { onSync, pendingCount } from "../lib/sync";
import { useAuth } from "../state/auth";
import Icon from "./Icon";
import { Avatar } from "./ui";

const STUDENT = [
  ["/", "home", "Inicio"], ["/entrenar", "dumbbell", "Entrenar"], ["/progreso", "chart", "Progreso"],
  ["/cuerpo", "body", "Cuerpo"], ["/membresia", "qr", "Mi QR"],
];
const TRAINER = [
  ["/", "home", "Inicio"], ["/entrenador/alumnos", "users", "Alumnos"], ["/entrenador/clases", "cal", "Clases"],
  ["/entrenador/rutinas", "list", "Rutinas"], ["/perfil", "user", "Perfil"],
];

export default function Layout() {
  const { me, gym, isTrainer, isStudent } = useAuth();
  const online = useOnline();
  const [pending, setPending] = useState(0);
  const loc = useLocation();
  const nav = useNavigate();
  const [mode, setMode] = useState(() => localStorage.getItem("entrenar.mode") || (isTrainer ? "trainer" : "student"));
  const trainerMode = isTrainer && (!isStudent || mode === "trainer");
  const tabs = gym?.nutrition === false ? (trainerMode ? TRAINER : STUDENT)
    : trainerMode ? [...TRAINER.slice(0, 4), ["/entrenador/nutricion", "food", "Nutrición"], TRAINER[4]]
      : [...STUDENT.slice(0, 2), ["/nutricion", "food", "Comidas"], ...STUDENT.slice(2)];

  useEffect(() => {
    pendingCount().then(setPending).catch(() => {});
    return onSync((e) => { if ("count" in e) setPending(e.count); else pendingCount().then(setPending); });
  }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [loc.pathname]);

  const switchMode = () => {
    const m = trainerMode ? "student" : "trainer";
    localStorage.setItem("entrenar.mode", m); setMode(m); nav("/");
  };

  return (
    <div className="shell">
      <header className="top">
        <button className="brand-btn" onClick={() => nav("/")}>
          {gym?.logo ? <img src={gym.logo} alt="" /> : <span className="brand-dot">{gym?.name?.[0] || "E"}</span>}
          <b>{gym?.name || "EntrenAR"}</b>
        </button>
        <div className="row" style={{ gap: 6 }}>
          {!online && <span className="pill warn"><Icon name="cloudOff" size={15} />Sin conexión</span>}
          {pending > 0 && <span className="pill info" title="Se envían solos cuando vuelva la señal"><Icon name="cloud" size={15} />{pending} por sincronizar</span>}
          {isTrainer && isStudent && <button className="pill" onClick={switchMode}>{trainerMode ? "Modo alumno" : "Modo entrenador"}</button>}
          <button className="icon-btn badge-wrap" onClick={() => nav("/notificaciones")}>
            <Icon name="bell" />{me?.unread > 0 && <i className="dot-badge">{me.unread}</i>}
          </button>
          <button className="icon-btn" onClick={() => nav("/perfil")}>
            <Avatar src={me?.member?.photo || me?.user?.avatar} initials={(me?.user?.first_name?.[0] || "") + (me?.user?.last_name?.[0] || "")} size={32} />
          </button>
        </div>
      </header>
      <main className="page" key={loc.pathname}><Outlet context={{ trainerMode }} /></main>
      <nav className={`tabbar ${tabs.length > 5 ? "six" : ""}`}>
        {tabs.map(([to, icon, label]) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "on" : "")}>
            <Icon name={icon} /><span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
