import { useState } from "react";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { Field, Loader, Sheet } from "../../components/ui";
import { post } from "../../lib/api";
import { useApi } from "../../lib/hooks";

export default function Exercises() {
  const { data, loading, reload } = useApi("/exercises/");
  const choices = useApi("/trainer/choices/");
  const toast = useToast();
  const [q, setQ] = useState("");
  const [g, setG] = useState("");
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState(null);
  const all = data?.results || [];
  const list = all.filter((e) => (!g || e.muscle_group === g) && (!q || e.name.toLowerCase().includes(q.toLowerCase())));
  const create = async () => {
    try { await post("/trainer/exercises/", form); toast("Ejercicio creado", "success"); setForm(null); reload(); }
    catch (e) { toast(e.message, "error"); }
  };
  if (loading && !data) return <Loader />;
  const c = choices.data;
  return (
    <div className="page-pad stack">
      <div className="row between"><h1 className="title">Ejercicios</h1>
        <button className="btn primary" onClick={() => setForm({ name: "", muscle_group: "chest", equipment: "barbell", tracking: "weight_reps", instructions: "", video_url: "" })}><Icon name="plus" size={18} />Nuevo</button></div>
      <div className="search-box"><Icon name="search" size={18} /><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Buscar entre ${all.length} ejercicios`} /></div>
      <div className="chips-scroll"><button className={`chip ${!g ? "on" : ""}`} onClick={() => setG("")}>Todos</button>
        {(c?.muscles || []).map(([k, l]) => <button key={k} className={`chip ${g === k ? "on" : ""}`} onClick={() => setG(k)}>{l}</button>)}</div>
      <div className="card list">{list.map((e) => (
        <button key={e.id} className="li" onClick={() => setSel(e)}><span style={{ textAlign: "left" }}><b>{e.name}</b><br /><small className="muted">{e.muscle_label} · {e.equipment_label}</small></span>
          {e.video_url ? <Icon name="play" size={18} /> : <Icon name="next" size={18} />}</button>))}</div>
      <Sheet open={!!sel} onClose={() => setSel(null)} title={sel?.name}>
        {sel && <div className="stack"><small className="muted">{sel.muscle_label}{sel.secondary_muscles && ` · ${sel.secondary_muscles}`} · {sel.equipment_label}</small>
          {sel.image && <img src={sel.image} alt="" className="ex-img" />}
          <p>{sel.instructions || "Sin indicaciones cargadas. Podés agregarlas desde el panel del gimnasio."}</p>
          {sel.video_url && <a className="btn block" href={sel.video_url} target="_blank" rel="noreferrer"><Icon name="play" size={18} />Ver video</a>}</div>}
      </Sheet>
      <Sheet open={!!form} onClose={() => setForm(null)} title="Nuevo ejercicio">
        {form && c && <div className="stack">
          <Field label="Nombre"><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <div className="grid2">
            <Field label="Grupo muscular"><select className="input" value={form.muscle_group} onChange={(e) => setForm({ ...form, muscle_group: e.target.value })}>{c.muscles.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
            <Field label="Equipamiento"><select className="input" value={form.equipment} onChange={(e) => setForm({ ...form, equipment: e.target.value })}>{c.equipment.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
          </div>
          <Field label="Se registra por"><select className="input" value={form.tracking} onChange={(e) => setForm({ ...form, tracking: e.target.value })}>{c.tracking.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
          <Field label="Técnica / indicaciones"><textarea className="input" value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} /></Field>
          <Field label="Link a video (YouTube, etc.)"><input className="input" value={form.video_url} onChange={(e) => setForm({ ...form, video_url: e.target.value })} /></Field>
          <button className="btn primary block" onClick={create}>Crear ejercicio</button></div>}
      </Sheet>
    </div>
  );
}
