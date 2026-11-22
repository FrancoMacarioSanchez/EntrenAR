import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Icon from "../../components/Icon";
import RestTimer from "../../components/RestTimer";
import { useToast } from "../../components/Toast";
import { Confetti, Empty, Loader, Sheet, Stepper } from "../../components/ui";
import { kv } from "../../lib/db";
import { mmss, today } from "../../lib/format";
import { useApi } from "../../lib/hooks";
import { enqueue, onSync, uuid } from "../../lib/sync";

const KEY = "workout:current";
const FEEL = ["😫", "😕", "🙂", "💪", "🔥"];

function newSet(n, rex, last, sug) {
  const prev = last?.sets?.[n - 1];
  return {
    client_uuid: uuid(), set_number: n, done: false,
    weight: sug?.weight ?? prev?.weight ?? rex?.target_weight ?? "",
    reps: "", repsHint: prev?.reps ?? rex?.reps_max ?? rex?.reps_min ?? "",
    to_failure: !!(rex?.to_failure && rex?.sets === n), rpe: "", duration_seconds: "",
  };
}

function buildBlocks(day) {
  return (day?.exercises || []).map((rex) => ({
    key: `r${rex.id}`, rex, exercise: rex.exercise, last: rex.last, suggestion: rex.suggestion,
    sets: Array.from({ length: rex.sets }, (_, i) => newSet(i + 1, rex, rex.last, rex.suggestion)),
  }));
}

export default function Workout() {
  const { dayId } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { data, loading } = useApi("/me/routine/");
  const [w, setW] = useState(null);           // sesión en curso
  const [rest, setRest] = useState(null);     // {seconds, startedAt}
  const [picker, setPicker] = useState(false);
  const [finish, setFinish] = useState(false);
  const [party, setParty] = useState(null);   // récords para festejar
  const [summary, setSummary] = useState(null);
  const [now, setNow] = useState(Date.now());
  const saveTimer = useRef();

  const routine = data?.routine;

  // restaurar o crear la sesión
  useEffect(() => {
    if (loading && !routine) return;
    (async () => {
      const cur = await kv.get(KEY).catch(() => null);
      if (cur && (!dayId || String(cur.routine_day || "libre") === String(dayId))) { setW(cur); return; }
      if (!dayId) return;
      const day = routine?.days.find((d) => String(d.id) === String(dayId));
      const fresh = {
        client_uuid: uuid(), routine_day: day?.id || null, day_name: day?.name || "Entrenamiento libre",
        date: today(), started_at: new Date().toISOString(), blocks: buildBlocks(day), notes: "", feeling: null,
      };
      setW(fresh);
      kv.set(KEY, fresh);
    })();
  }, [dayId, routine, loading]);

  // persistir cada cambio (por si se cierra la app)
  useEffect(() => {
    if (!w) return;
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => kv.set(KEY, w).catch(() => {}), 250);
  }, [w]);

  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);

  // festejar récords cuando el servidor los confirma
  useEffect(() => onSync((e) => {
    if (e.type !== "synced") return;
    const recs = e.results.flatMap((r) => r.records || []);
    const ach = e.results.flatMap((r) => r.achievements || []);
    if (recs.length) {
      setParty(recs);
      navigator.vibrate?.([60, 40, 60, 40, 120]);
      setTimeout(() => setParty(null), 4200);
    }
    ach.forEach((a) => toast(`${a.icon} ¡Logro desbloqueado: ${a.title}!`, "success", 5000));
  }), [toast]);

  const payload = useCallback((ws, finished) => ({
    client_uuid: ws.client_uuid, routine_day: ws.routine_day, date: ws.date, started_at: ws.started_at,
    finished_at: finished ? new Date().toISOString() : null, feeling: ws.feeling, notes: ws.notes,
    sets: ws.blocks.flatMap((b) => b.sets.filter((s) => s.done || s.deleted).map((s) => ({
      client_uuid: s.client_uuid, deleted: !!s.deleted, exercise: b.exercise.id, routine_exercise: b.rex?.id || null,
      set_number: s.set_number, reps: s.reps === "" ? null : Number(s.reps), weight: s.weight === "" ? null : Number(s.weight),
      duration_seconds: s.duration_seconds === "" ? null : Number(s.duration_seconds), to_failure: s.to_failure,
      rpe: s.rpe === "" ? null : Number(s.rpe), created_at: s.done_at,
    }))),
  }), []);

  const update = (bi, si, patch) => setW((x) => {
    const blocks = x.blocks.map((b, i) => i !== bi ? b : { ...b, sets: b.sets.map((s, j) => (j === si ? { ...s, ...patch } : s)) });
    return { ...x, blocks };
  });

  const complete = (bi, si) => {
    const b = w.blocks[bi], s = b.sets[si];
    const tracking = b.exercise.tracking;
    if (!s.done) {
      const reps = s.reps === "" ? s.repsHint : s.reps;
      if (tracking !== "time" && tracking !== "distance_time" && (reps === "" || reps == null)) {
        toast("Cargá las repeticiones", "error"); return;
      }
      const patch = { done: true, reps: tracking === "time" ? s.reps : reps, done_at: new Date().toISOString() };
      const next = { ...w, blocks: w.blocks.map((bb, i) => i !== bi ? bb : { ...bb, sets: bb.sets.map((ss, j) => (j === si ? { ...ss, ...patch } : ss)) }) };
      setW(next);
      kv.set(KEY, next);
      enqueue("session", payload(next, false)); // guarda la serie y detecta récords
      if (b.rex?.rest_seconds) setRest({ seconds: b.rex.rest_seconds, startedAt: Date.now() });
      navigator.vibrate?.(30);
    } else {
      update(bi, si, { done: false });
    }
  };

  const addSet = (bi) => setW((x) => ({ ...x, blocks: x.blocks.map((b, i) => {
    if (i !== bi) return b;
    const lastSet = b.sets[b.sets.length - 1];
    const ns = newSet(b.sets.length + 1, b.rex, b.last, b.suggestion);
    if (lastSet) { ns.weight = lastSet.weight; ns.repsHint = lastSet.reps || lastSet.repsHint; }
    return { ...b, sets: [...b.sets, ns] };
  }) }));

  const removeSet = (bi, si) => setW((x) => ({ ...x, blocks: x.blocks.map((b, i) => i !== bi ? b : {
    ...b, sets: b.sets.map((s, j) => (j === si ? (s.done ? { ...s, deleted: true, done: false } : null) : s)).filter(Boolean),
  }) }));

  const addExercise = (ex) => {
    setW((x) => ({ ...x, blocks: [...x.blocks, { key: `e${ex.id}-${Date.now()}`, rex: null, exercise: ex, last: null,
      suggestion: null, sets: [newSet(1, null, null, null), newSet(2, null, null, null), newSet(3, null, null, null)] }] }));
    setPicker(false);
  };

  const doFinish = async () => {
    const done = w.blocks.flatMap((b) => b.sets.filter((s) => s.done));
    const p = payload(w, true);
    await enqueue("session", p);
    await kv.del(KEY);
    const vol = done.reduce((a, s) => a + (Number(s.weight) || 0) * (Number(s.reps) || 0), 0);
    setSummary({ sets: done.length, volume: Math.round(vol), minutes: Math.round((Date.now() - new Date(w.started_at)) / 60000),
      exercises: w.blocks.filter((b) => b.sets.some((s) => s.done)).length });
    setFinish(false);
  };

  const discard = async () => {
    if (!confirm("¿Descartar el entrenamiento? Las series ya enviadas quedan guardadas.")) return;
    await kv.del(KEY);
    nav("/");
  };

  const progress = useMemo(() => {
    if (!w) return 0;
    const all = w.blocks.flatMap((b) => b.sets.filter((s) => !s.deleted));
    return all.length ? all.filter((s) => s.done).length / all.length : 0;
  }, [w]);

  if (summary) return (
    <div className="page-pad stack center">
      <Confetti show />
      <div className="done-badge">🏁</div>
      <h1>¡Entrenamiento terminado!</h1>
      <div className="grid3">
        <div className="mini"><small>Series</small><b>{summary.sets}</b></div>
        <div className="mini"><small>Volumen</small><b>{(summary.volume / 1000).toFixed(1)} t</b></div>
        <div className="mini"><small>Duración</small><b>{summary.minutes} min</b></div>
      </div>
      <p className="muted">Si no tenías señal, se sincroniza solo cuando vuelva la conexión.</p>
      <button className="btn primary lg block" onClick={() => nav("/progreso")}>Ver mi progreso</button>
      <button className="btn block" onClick={() => nav("/")}>Volver al inicio</button>
    </div>
  );

  if (!dayId && !w) {
    if (loading && !routine) return <Loader />;
    return (
      <div className="page-pad stack">
        <h1 className="title">¿Qué entrenás hoy?</h1>
        {routine ? routine.days.map((d) => (
          <button key={d.id} className={`card day-pick ${d.id === routine.next_day ? "next" : ""}`} onClick={() => nav(`/entrenar/${d.id}`)}>
            <div><b>{d.name}</b>{d.id === routine.next_day && <span className="pill info">Te toca</span>}<br />
              <small className="muted">{d.exercises.map((e) => e.exercise.name).slice(0, 4).join(" · ")}{d.exercises.length > 4 ? "…" : ""}</small></div>
            <Icon name="next" />
          </button>
        )) : <Empty icon="list" title="Sin rutina asignada">Podés registrar un entrenamiento libre.</Empty>}
        <button className="btn block" onClick={() => nav("/entrenar/libre")}><Icon name="plus" size={18} />Entrenamiento libre</button>
      </div>
    );
  }
  if (!w) return <Loader />;

  const elapsed = Math.floor((now - new Date(w.started_at).getTime()) / 1000);

  return (
    <div className="workout">
      <Confetti show={!!party} />
      {party && <div className="pr-pop"><Icon name="trophy" size={34} /><b>¡NUEVO RÉCORD!</b>
        {party.map((r) => <span key={r.id}>{r.exercise_name}: {r.label}</span>)}</div>}

      <div className="wk-head">
        <button className="icon-btn" onClick={() => nav("/")}><Icon name="back" /></button>
        <div><b>{w.day_name}</b><small>{mmss(elapsed)} · {Math.round(progress * 100)}%</small></div>
        <button className="btn sm primary" onClick={() => setFinish(true)}>Terminar</button>
        <div className="wk-progress"><span style={{ width: `${progress * 100}%` }} /></div>
      </div>

      <div className="page-pad stack">
        {w.blocks.length === 0 && <Empty icon="dumbbell" title="Agregá tu primer ejercicio" />}
        {w.blocks.map((b, bi) => {
          const t = b.exercise.tracking;
          const timeOnly = t === "time" || t === "distance_time";
          return (
            <section key={b.key} className={`card ex-block ${b.rex?.superset_group ? "superset" : ""}`}>
              <div className="ex-head">
                <div>
                  {b.rex?.superset_group && <span className="pill">Superserie {b.rex.superset_group}</span>}
                  <h3>{b.exercise.name}</h3>
                  <small className="muted">{b.exercise.muscle_label}
                    {b.rex && <> · {b.rex.sets}×{b.rex.reps_label || "—"}{b.rex.rest_seconds ? ` · desc. ${mmss(b.rex.rest_seconds)}` : ""}{b.rex.tempo ? ` · tempo ${b.rex.tempo}` : ""}{b.rex.rpe_target ? ` · RPE ${b.rex.rpe_target}` : ""}</>}</small>
                </div>
                {b.exercise.video_url && <a className="icon-btn" href={b.exercise.video_url} target="_blank" rel="noreferrer"><Icon name="play" size={18} /></a>}
              </div>
              {b.rex?.notes && <p className="note"><Icon name="msg" size={14} /> {b.rex.notes}</p>}
              {(b.suggestion || b.last) && <div className="hint">
                {b.last && <small>Última vez ({b.last.date}): {b.last.sets.map((s) => `${s.weight ? s.weight + "×" : ""}${s.reps ?? ""}`).join(" · ")}</small>}
                {b.suggestion && <small className="sug"><Icon name="fire" size={14} /> {b.suggestion.text}</small>}
              </div>}
              <div className="set-grid head"><span>#</span><span>{timeOnly ? "Seg." : "Kg"}</span><span>{timeOnly ? "" : "Reps"}</span><span>Fallo</span><span /></div>
              {b.sets.map((s, si) => s.deleted ? null : (
                <div key={s.client_uuid} className={`set-grid ${s.done ? "done" : ""}`}>
                  <button className="set-n" onClick={() => removeSet(bi, si)} title="Quitar serie">{s.set_number}</button>
                  {timeOnly
                    ? <Stepper value={s.duration_seconds} onChange={(v) => update(bi, si, { duration_seconds: v })} step={5} inputMode="numeric" />
                    : <Stepper value={s.weight} onChange={(v) => update(bi, si, { weight: v })} step={b.exercise.equipment === "dumbbell" ? 1 : 2.5} placeholder="0" />}
                  {timeOnly ? <span /> : <Stepper value={s.reps} onChange={(v) => update(bi, si, { reps: v })} step={1} inputMode="numeric" placeholder={String(s.repsHint ?? "")} />}
                  <button className={`fail ${s.to_failure ? "on" : ""}`} onClick={() => update(bi, si, { to_failure: !s.to_failure })}>F</button>
                  <button className={`ok-btn ${s.done ? "on" : ""}`} onClick={() => complete(bi, si)}><Icon name="check" size={20} stroke={3} /></button>
                </div>
              ))}
              <button className="btn sm ghost" onClick={() => addSet(bi)}><Icon name="plus" size={16} />Agregar serie</button>
            </section>
          );
        })}
        <button className="btn block" onClick={() => setPicker(true)}><Icon name="plus" size={18} />Agregar ejercicio</button>
        <button className="btn ghost block danger-text" onClick={discard}>Descartar entrenamiento</button>
      </div>

      {rest && <RestTimer seconds={rest.seconds} startedAt={rest.startedAt} onDone={() => setRest(null)}
        onAdd={(s) => setRest((r) => ({ ...r, seconds: r.seconds + s }))} />}

      <ExercisePicker open={picker} onClose={() => setPicker(false)} onPick={addExercise} />

      <Sheet open={finish} onClose={() => setFinish(false)} title="¿Cómo te sentiste?">
        <div className="stack">
          <div className="feel">{FEEL.map((f, i) => (
            <button key={i} className={w.feeling === i + 1 ? "on" : ""} onClick={() => setW({ ...w, feeling: i + 1 })}>{f}</button>))}</div>
          <textarea className="input" placeholder="Notas para tu entrenador (opcional)" value={w.notes}
            onChange={(e) => setW({ ...w, notes: e.target.value })} />
          <button className="btn primary lg block" onClick={doFinish}>Guardar entrenamiento</button>
        </div>
      </Sheet>
    </div>
  );
}

export function ExercisePicker({ open, onClose, onPick }) {
  const { data } = useApi(open ? "/exercises/" : null);
  const [q, setQ] = useState("");
  const [g, setG] = useState("");
  const list = (data?.results || []).filter((e) => (!g || e.muscle_group === g) &&
    (!q || e.name.toLowerCase().includes(q.toLowerCase())));
  const groups = [...new Map((data?.results || []).map((e) => [e.muscle_group, e.muscle_label])).entries()];
  return (
    <Sheet open={open} onClose={onClose} title="Elegí un ejercicio" tall>
      <div className="search-box"><Icon name="search" size={18} /><input className="input" placeholder="Buscar…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus /></div>
      <div className="chips-scroll">
        <button className={`chip ${!g ? "on" : ""}`} onClick={() => setG("")}>Todos</button>
        {groups.map(([k, l]) => <button key={k} className={`chip ${g === k ? "on" : ""}`} onClick={() => setG(k)}>{l}</button>)}
      </div>
      {!data ? <Loader /> : <div className="list">{list.map((e) => (
        <button key={e.id} className="li" onClick={() => onPick(e)}>
          <span style={{ textAlign: "left" }}><b>{e.name}</b><br /><small className="muted">{e.muscle_label} · {e.equipment_label}</small></span>
          <Icon name="plus" size={18} /></button>))}
        {!list.length && <p className="muted center">No encontramos ejercicios.</p>}</div>}
    </Sheet>
  );
}

