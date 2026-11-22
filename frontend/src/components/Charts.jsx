// Gráficos SVG livianos (sin dependencias).
import { useMemo, useState } from "react";
import { dateShort } from "../lib/format";

export function LineChart({ points, height = 180, unit = "", color = "var(--brand)", yFormat = (v) => v }) {
  const [hover, setHover] = useState(null);
  const W = 340, H = height, P = { l: 34, r: 10, t: 14, b: 22 };
  const pts = points.filter((p) => p.y != null);
  const { path, area, xs, ys, min, max } = useMemo(() => {
    if (!pts.length) return {};
    let min = Math.min(...pts.map((p) => p.y)), max = Math.max(...pts.map((p) => p.y));
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.12; min -= pad; max += pad;
    const xs = pts.map((_, i) => P.l + (pts.length === 1 ? (W - P.l - P.r) / 2 : (i * (W - P.l - P.r)) / (pts.length - 1)));
    const ys = pts.map((p) => P.t + (1 - (p.y - min) / (max - min)) * (H - P.t - P.b));
    let path = `M${xs[0]},${ys[0]}`;
    for (let i = 1; i < xs.length; i++) {
      const cx = (xs[i - 1] + xs[i]) / 2;
      path += ` C${cx},${ys[i - 1]} ${cx},${ys[i]} ${xs[i]},${ys[i]}`;
    }
    const area = `${path} L${xs[xs.length - 1]},${H - P.b} L${xs[0]},${H - P.b} Z`;
    return { path, area, xs, ys, min, max };
  }, [pts, H]);
  if (!pts.length) return <div className="chart-empty">Todavía no hay datos para graficar.</div>;
  const ticks = [0, 0.5, 1].map((t) => min + t * (max - min));
  const h = hover ?? pts.length - 1;
  return (
    <div className="chart">
      <div className="chart-tip"><b>{yFormat(pts[h].y)}{unit}</b> <small>{pts[h].label ?? dateShort(pts[h].x)}</small></div>
      <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}
        onTouchEnd={() => setTimeout(() => setHover(null), 1500)}>
        <defs><linearGradient id="lg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".28" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
        {ticks.map((t, i) => {
          const y = P.t + (1 - (t - min) / (max - min)) * (H - P.t - P.b);
          return <g key={i}><line x1={P.l} x2={W - P.r} y1={y} y2={y} stroke="var(--line)" strokeDasharray="3 4" />
            <text x={P.l - 6} y={y + 4} textAnchor="end" className="axis">{Math.round(t * 10) / 10}</text></g>;
        })}
        <path d={area} fill="url(#lg)" />
        <path d={path} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" className="draw" />
        {xs.map((x, i) => (
          <g key={i} onMouseEnter={() => setHover(i)} onTouchStart={() => setHover(i)}>
            <rect x={x - 12} y={0} width={24} height={H} fill="transparent" />
            <circle cx={x} cy={ys[i]} r={i === h ? 6 : 3.5} fill={i === h ? color : "var(--surface)"} stroke={color} strokeWidth="2.5" />
          </g>
        ))}
        <text x={P.l} y={H - 4} className="axis">{pts[0].label ?? dateShort(pts[0].x)}</text>
        <text x={W - P.r} y={H - 4} textAnchor="end" className="axis">{pts[pts.length - 1].label ?? dateShort(pts[pts.length - 1].x)}</text>
      </svg>
    </div>
  );
}

export function Bars({ items, height = 140, color = "var(--brand)", format = (v) => v }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="bars" style={{ height }}>
      {items.map((it, i) => (
        <div className="bar" key={i} title={`${it.label}: ${format(it.value)}`}>
          <span style={{ height: `${Math.max(3, (it.value / max) * 100)}%`, background: it.color || color, animationDelay: `${i * 35}ms` }} />
          <small>{it.label}</small>
        </div>
      ))}
    </div>
  );
}

export function HBars({ items, format = (v) => v }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="hbars">
      {items.map((it) => (
        <div key={it.label} className="hbar">
          <div className="row between"><span>{it.label}</span><b>{format(it.value)}</b></div>
          <div className="track"><span style={{ width: `${(it.value / max) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  );
}
