import { Component, useEffect, useRef, useState } from "react";
import Icon from "./Icon";

export function Loader({ text = "Cargando…" }) {
  return <div className="loader"><span className="spinner" />{text}</div>;
}

export function Empty({ icon = "info", title, children, action }) {
  return (
    <div className="empty">
      <div className="empty-ico"><Icon name={icon} size={30} /></div>
      {title && <h3>{title}</h3>}
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Avatar({ src, initials, size = 44 }) {
  return src ? <img className="avatar" src={src} alt="" style={{ width: size, height: size }} />
    : <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.36 }}>{initials}</span>;
}

export function Stat({ label, value, sub, accent }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <b className="stat-value" style={accent ? { color: accent } : undefined}>{value}</b>
      {sub && <small>{sub}</small>}
    </div>
  );
}

export function Ring({ value = 0, max = 100, size = 120, stroke = 12, label, sub, color = "var(--brand)" }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, max ? value / max : 0));
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--line)" strokeWidth={stroke} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct)} transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dashoffset 1s cubic-bezier(.2,.8,.2,1)" }} />
      </svg>
      <div className="ring-in"><b>{label}</b>{sub && <small>{sub}</small>}</div>
    </div>
  );
}

export function Segmented({ options, value, onChange }) {
  return (
    <div className="seg">
      {options.map(([v, l]) => (
        <button key={v} className={v === value ? "on" : ""} onClick={() => onChange(v)} type="button">{l}</button>
      ))}
    </div>
  );
}

export function Stepper({ value, onChange, step = 1, min = 0, suffix = "", inputMode = "decimal", placeholder }) {
  const n = value === "" || value == null ? null : Number(value);
  const set = (v) => onChange(v == null ? "" : String(Math.max(min, Math.round(v * 100) / 100)));
  return (
    <div className="stepper">
      <button type="button" onClick={() => set((n ?? 0) - step)} aria-label="menos"><Icon name="minus" size={18} /></button>
      <input value={value ?? ""} inputMode={inputMode} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value.replace(",", "."))} onFocus={(e) => e.target.select()} />
      {suffix && <span className="suffix">{suffix}</span>}
      <button type="button" onClick={() => set((n ?? 0) + step)} aria-label="más"><Icon name="plus" size={18} /></button>
    </div>
  );
}

export function Sheet({ open, onClose, title, children, tall }) {
  const ref = useRef();
  useEffect(() => {
    if (!open) return;
    const k = (e) => e.key === "Escape" && onClose?.();
    document.addEventListener("keydown", k);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", k); document.body.style.overflow = ""; };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="sheet-backdrop" onClick={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className={`sheet ${tall ? "tall" : ""}`} ref={ref}>
        <div className="sheet-handle" />
        {title && <div className="sheet-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose}><Icon name="x" /></button></div>}
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  );
}

export function Confetti({ show }) {
  const [pieces] = useState(() => Array.from({ length: 70 }, (_, i) => ({
    left: Math.random() * 100, delay: Math.random() * 0.4, dur: 1.6 + Math.random() * 1.2, rot: Math.random() * 360,
    color: ["#ff5a1f", "#facc15", "#22c55e", "#3b82f6", "#ec4899", "#a855f7"][i % 6],
  })));
  if (!show) return null;
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p, i) => <i key={i} style={{ left: p.left + "%", background: p.color, animationDelay: p.delay + "s",
        animationDuration: p.dur + "s", transform: `rotate(${p.rot}deg)` }} />)}
    </div>
  );
}

// div (no <label>): un <label> envolviendo el Stepper hacía que tocar el título activara el botón «−».
export function Field({ label, children, hint, error }) {
  return <div className={`field ${error ? "has-error" : ""}`}><span>{label}</span>{children}
    {error ? <small className="field-error">{error}</small> : hint && <small>{hint}</small>}</div>;
}

export class ErrorBoundary extends Component {
  constructor(p) { super(p); this.state = { failed: false }; }
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(e) { console.warn("Componente con error:", e); }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}
