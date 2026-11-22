import { useEffect, useState } from "react";
import Icon from "./Icon";

// Invita a instalar la PWA (Android: botón nativo · iPhone: instrucciones).
export default function InstallPrompt() {
  const [evt, setEvt] = useState(null);
  const [hidden, setHidden] = useState(() => localStorage.getItem("entrenar.install.hide") === "1");
  const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  useEffect(() => {
    const h = (e) => { e.preventDefault(); setEvt(e); };
    window.addEventListener("beforeinstallprompt", h);
    return () => window.removeEventListener("beforeinstallprompt", h);
  }, []);
  if (standalone || hidden || (!evt && !ios)) return null;
  const close = () => { localStorage.setItem("entrenar.install.hide", "1"); setHidden(true); };
  return (
    <div className="install card">
      <Icon name="download" />
      <div style={{ flex: 1 }}>
        <b>Instalá la app</b>
        <small>{ios ? "Tocá Compartir y después «Agregar a inicio»." : "Acceso directo, pantalla completa y notificaciones."}</small>
      </div>
      {evt && <button className="btn sm primary" onClick={async () => { evt.prompt(); await evt.userChoice; setEvt(null); }}>Instalar</button>}
      <button className="icon-btn" onClick={close}><Icon name="x" size={18} /></button>
    </div>
  );
}
