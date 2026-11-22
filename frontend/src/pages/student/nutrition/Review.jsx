import { useEffect, useMemo, useState } from "react";
import Icon from "../../../components/Icon";
import { useToast } from "../../../components/Toast";
import { Sheet, Stepper } from "../../../components/ui";
import { api, del, get, post } from "../../../lib/api";
import { num } from "../../../lib/format";
import { MEALS, itemFromFood, scale, sum, toPayload } from "../../../lib/nutrition";
import { FoodSearch, MacroLine } from "./parts";

// Pantalla de confirmación: el alumno ajusta gramos, cambia alimentos o agrega/quita antes de guardar.
export default function Review({ draft, onClose, onSaved }) {
  const toast = useToast();
  const [items, setItems] = useState([]);
  const [mealType, setMealType] = useState("almuerzo");
  const [picker, setPicker] = useState(null); // null | "add" | key del ítem a reemplazar
  const [habitual, setHabitual] = useState(false);
  const [habitualName, setHabitualName] = useState("");
  const [saving, setSaving] = useState(false);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    if (!draft) return;
    setItems(draft.items); setMealType(draft.meal_type); setHabitual(false);
    setHabitualName(draft.meal_name || ""); setPicker(null);
  }, [draft]);
  useEffect(() => { if (picker && !recent.length) get("/me/nutrition/recent/").then(setRecent).catch(() => {}); }, [picker]); // eslint-disable-line react-hooks/exhaustive-deps

  const withMacros = useMemo(() => items.map((it) => ({ ...it, m: scale(it.per100, it.grams) })), [items]);
  const total = sum(withMacros, (i) => i.m);

  if (!draft) return null;
  const update = (key, patch) => setItems((l) => l.map((it) => (it.key === key ? { ...it, ...patch } : it)));
  const swap = (key, food) => update(key, { food_id: food.id, food, name: food.name, per100: food.per100, source: "catalogo" });
  const remove = (key) => setItems((l) => l.filter((it) => it.key !== key));

  const pick = (food) => {
    if (picker === "add") setItems((l) => [...l, itemFromFood(food)]);
    else swap(picker, food);
    setPicker(null);
  };

  const save = async () => {
    if (!items.length) { toast("Agregá al menos un alimento.", "warn"); return; }
    if (items.some((i) => !(Number(i.grams) > 0))) { toast("Revisá los gramos: tienen que ser mayores a 0.", "warn"); return; }
    setSaving(true);
    try {
      const body = { meal_type: mealType, date: draft.date, items: toPayload(items), source: draft.source, ai_request: draft.ai_request };
      const meal = draft.meal_id ? await api(`/me/nutrition/meals/${draft.meal_id}/`, { method: "PUT", body })
        : await post("/me/nutrition/meals/", body);
      if (habitual && habitualName.trim()) await post(`/me/nutrition/meals/${meal.id}/habitual/`, { name: habitualName.trim() });
      toast(draft.meal_id ? "Comida actualizada" : "Comida registrada", "ok");
      onSaved();
    } catch (e) { toast(e.message, "bad"); } finally { setSaving(false); }
  };

  const removeMeal = async () => {
    if (!confirm("¿Borrar esta comida?")) return;
    await del(`/me/nutrition/meals/${draft.meal_id}/`);
    toast("Comida borrada", "ok"); onSaved();
  };

  return (
    <Sheet open={!!draft} onClose={onClose} title={picker ? (picker === "add" ? "Agregar alimento" : "Cambiar alimento") : draft.meal_id ? "Editar comida" : "Revisá y confirmá"} tall>
      {picker ? (
        <div className="stack"><FoodSearch onPick={pick} recent={recent} />
          <button className="btn block" onClick={() => setPicker(null)}>Volver</button></div>
      ) : (
        <div className="stack review">
          {draft.image && <img className="review-photo" src={draft.image} alt="" />}
          {draft.meal_name && <h3>{draft.meal_name}</h3>}
          {draft.demo && <div className="card tip"><Icon name="info" size={18} />Respuesta de demostración: falta configurar la clave de Gemini en el servidor.</div>}
          {draft.notes && !draft.demo && <div className="card tip"><Icon name="info" size={18} />{draft.notes}</div>}
          {draft.ai_request && <small className="muted">La IA estimó las porciones: ajustá lo que no coincida antes de guardar.</small>}

          <div className="seg meal-seg">{MEALS.map(([v, l]) => <button key={v} type="button" className={v === mealType ? "on" : ""} onClick={() => setMealType(v)}>{l}</button>)}</div>

          {withMacros.map((it) => (
            <div key={it.key} className={`review-item ${it.confidence === "baja" ? "low" : ""}`}>
              <div className="row between top-align">
                <div className="grow">
                  <b>{it.name}</b>
                  {it.source === "ia" && <em className="pill xs warn" title="No está en la base: valores estimados por la IA">estimado</em>}
                  {it.confidence === "baja" && <em className="pill xs bad">revisar</em>}
                  {it.ai_name && it.ai_name !== it.name && <><br /><small className="muted">La IA vio: {it.ai_name}</small></>}
                </div>
                <button className="icon-btn" onClick={() => setPicker(it.key)} aria-label="Cambiar"><Icon name="rotate" size={18} /></button>
                <button className="icon-btn" onClick={() => remove(it.key)} aria-label="Quitar"><Icon name="trash" size={18} /></button>
              </div>
              {it.alternatives?.length > 0 && it.food_id === it.original_food_id && (
                <div className="chips-scroll"><small className="muted">¿Era otra cosa?</small>
                  {it.alternatives.map((a) => <button key={a.id} className="chip sm" onClick={() => swap(it.key, a)}>{a.name}</button>)}</div>
              )}
              <div className="row review-qty">
                <Stepper value={String(it.grams)} step={it.grams >= 100 ? 10 : 5} min={1} suffix={it.food?.is_liquid ? "ml" : "g"}
                  onChange={(v) => update(it.key, { grams: v, portion: "" })} />
                {(it.food?.portions || []).slice(0, 3).map((p) => (
                  <button key={p.label} className="chip sm" onClick={() => update(it.key, { grams: p.grams, portion: `1 ${p.label}` })}>1 {p.label}</button>
                ))}
              </div>
              {it.portion && <small className="muted">{it.portion}</small>}
              <MacroLine m={it.m} />
            </div>
          ))}
          <button className="btn dashed block" onClick={() => setPicker("add")}><Icon name="plus" size={18} />Agregar otro alimento</button>

          <div className="card review-total">
            <div className="row between"><span>Total</span><b>{num(total.kcal, 0)} kcal</b></div>
            <MacroLine m={total} />
          </div>

          {!draft.meal_id && (
            <label className="check-row">
              <input type="checkbox" checked={habitual} onChange={(e) => setHabitual(e.target.checked)} />
              <span>Guardar como comida habitual</span>
            </label>
          )}
          {habitual && <input className="input" placeholder="Nombre, ej: Desayuno de siempre" value={habitualName} onChange={(e) => setHabitualName(e.target.value)} />}

          <button className="btn primary lg block" disabled={saving} onClick={save}>{saving ? "Guardando…" : draft.meal_id ? "Guardar cambios" : "Confirmar comida"}</button>
          {draft.meal_id && <button className="btn danger block" onClick={removeMeal}><Icon name="trash" size={18} />Borrar comida</button>}
        </div>
      )}
    </Sheet>
  );
}

// Comida ya guardada → borrador editable (los valores por 100 g se reconstruyen desde la foto guardada).
export function draftFromMeal(meal) {
  return {
    meal_id: meal.id, meal_type: meal.meal_type, date: meal.date, source: meal.source, image: meal.image,
    items: meal.items.map((i) => {
      const k = i.grams ? 100 / i.grams : 0;
      return { key: `m${i.id}`, food_id: i.food_id, name: i.name, grams: i.grams, portion: i.portion,
        per100: { kcal: i.kcal * k, protein: i.protein * k, carbs: i.carbs * k, fat: i.fat * k, fiber: i.fiber == null ? null : i.fiber * k },
        source: i.from_ai && !i.food_id ? "ia" : "catalogo" };
    }),
  };
}
