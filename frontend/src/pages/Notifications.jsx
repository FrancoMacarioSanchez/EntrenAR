import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import { Empty, Loader } from "../components/ui";
import { post } from "../lib/api";
import { ago } from "../lib/format";
import { useApi } from "../lib/hooks";
import { useAuth } from "../state/auth";

const ICON = { pr: "trophy", payment: "card", membership: "card", class: "cal", routine: "list", feedback: "msg", note: "msg", birthday: "star" };

export default function Notifications() {
  const { data, loading } = useApi("/notifications/");
  const { reload } = useAuth();
  const nav = useNavigate();
  useEffect(() => { post("/notifications/read/").then(reload).catch(() => {}); }, [reload]);
  if (loading && !data) return <Loader />;
  const items = data?.results || [];
  return (
    <div className="page-pad">
      <h1 className="title">Notificaciones</h1>
      {!items.length ? <Empty icon="bell" title="Nada por acá">Te avisamos de récords, pagos, clases y mensajes de tu entrenador.</Empty> :
        <div className="card list">{items.map((n) => (
          <button key={n.id} className={`li notif ${n.is_read ? "" : "unread"}`} onClick={() => n.url && nav(n.url.replace(/^\/app/, "") || "/")}>
            <span className="row" style={{ gap: 12, alignItems: "flex-start" }}><span className="ico-bubble"><Icon name={ICON[n.kind] || "bell"} size={18} /></span>
              <span style={{ textAlign: "left" }}><b>{n.title}</b><br /><small>{n.body}</small></span></span>
            <small className="muted nowrap">{ago(n.created_at)}</small></button>))}</div>}
    </div>
  );
}
