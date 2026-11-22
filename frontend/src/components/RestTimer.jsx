import { useEffect, useRef, useState } from "react";
import { mmss } from "../lib/format";
import Icon from "./Icon";

// Temporizador de descanso flotante (vibra y suena al terminar).
export default function RestTimer({ seconds, startedAt, onDone, onAdd }) {
  const [now, setNow] = useState(Date.now());
  const fired = useRef(false);
  useEffect(() => {
    fired.current = false;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [startedAt]);
  const left = Math.max(0, seconds - (now - startedAt) / 1000);
  useEffect(() => {
    if (left <= 0 && !fired.current) {
      fired.current = true;
      navigator.vibrate?.([200, 100, 200]);
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [0, 0.25].forEach((d) => {
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
          g.gain.setValueAtTime(0.25, ctx.currentTime + d); g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + d + 0.2);
          o.start(ctx.currentTime + d); o.stop(ctx.currentTime + d + 0.22);
        });
      } catch { /* sin audio */ }
      setTimeout(() => onDone?.(), 1200);
    }
  }, [left, onDone]);
  const pct = 1 - left / seconds;
  return (
    <div className={`rest ${left <= 0 ? "done" : ""}`}>
      <div className="rest-bar" style={{ transform: `scaleX(${pct})` }} />
      <Icon name="timer" />
      <div className="rest-txt"><small>{left <= 0 ? "¡A la próxima serie!" : "Descanso"}</small><b>{mmss(left)}</b></div>
      <button className="chip" onClick={() => onAdd?.(15)}>+15s</button>
      <button className="chip" onClick={onDone}>Saltar</button>
    </div>
  );
}
