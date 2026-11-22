import jsQR from "jsqr";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "../../components/Icon";

function extractKey(raw) {
  try { const u = new URL(raw); return u.searchParams.get("k") || raw; } catch { return raw; }
}

// Escáner del QR de la entrada. Usa BarcodeDetector si existe (Android) y si no jsQR (iPhone, Windows, etc.).
// Si no hay cámara (o la página no es HTTPS) se puede escribir el código corto del cartel.
export default function Scan() {
  const video = useRef(null);
  const canvas = useRef(null);
  const nav = useNavigate();
  const [state, setState] = useState("starting"); // starting | scanning | nocamera | denied
  const [code, setCode] = useState("");
  const [torch, setTorch] = useState(null);

  useEffect(() => {
    let stream, raf, stopped = false, detector = null;
    const go = (raw) => {
      stopped = true;
      navigator.vibrate?.(40);
      nav(`/ingreso?k=${encodeURIComponent(extractKey(raw))}`, { replace: true });
    };
    (async () => {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) { setState("nocamera"); return; }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      } catch (e) {
        setState(e?.name === "NotAllowedError" ? "denied" : "nocamera");
        return;
      }
      if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
      const v = video.current;
      v.srcObject = stream;
      v.setAttribute("playsinline", "true");
      await v.play().catch(() => {});
      setState("scanning");
      const track = stream.getVideoTracks()[0];
      if (track?.getCapabilities?.().torch) setTorch(false);
      if ("BarcodeDetector" in window) {
        try { detector = new window.BarcodeDetector({ formats: ["qr_code"] }); } catch { detector = null; }
      }
      const ctx = canvas.current.getContext("2d", { willReadFrequently: true });
      let busy = false;
      const loop = async () => {
        if (stopped) return;
        raf = requestAnimationFrame(loop);
        if (busy || v.readyState < 2) return;
        busy = true;
        try {
          if (detector) {
            const codes = await detector.detect(v);
            if (codes[0]?.rawValue) return go(codes[0].rawValue);
          } else {
            const w = 480, h = Math.round((v.videoHeight / v.videoWidth) * w) || 360;
            canvas.current.width = w; canvas.current.height = h;
            ctx.drawImage(v, 0, 0, w, h);
            const img = ctx.getImageData(0, 0, w, h);
            const r = jsQR(img.data, w, h, { inversionAttempts: "dontInvert" });
            if (r?.data) return go(r.data);
          }
        } catch { /* frame no listo */ } finally { busy = false; }
      };
      loop();
    })();
    return () => { stopped = true; cancelAnimationFrame(raf); stream?.getTracks().forEach((t) => t.stop()); };
  }, [nav]);

  const toggleTorch = async () => {
    const track = video.current?.srcObject?.getVideoTracks?.()[0];
    if (!track) return;
    try { await track.applyConstraints({ advanced: [{ torch: !torch }] }); setTorch(!torch); } catch { /* sin linterna */ }
  };

  const submitCode = (e) => {
    e.preventDefault();
    const c = code.trim();
    if (c.length >= 6) nav(`/ingreso?k=${encodeURIComponent(c)}`);
  };

  return (
    <div className="page-pad stack">
      <h1 className="title">Ingresar al gimnasio</h1>
      {(state === "starting" || state === "scanning") && (
        <div className="scanner">
          <video ref={video} playsInline muted />
          <div className="scan-frame"><i /></div>
          <p>{state === "starting" ? "Abriendo la cámara…" : "Apuntá al QR de la entrada"}</p>
          {torch !== null && <button className="torch" onClick={toggleTorch}>{torch ? "Apagar linterna" : "Linterna"}</button>}
        </div>
      )}
      {state === "denied" && <div className="card tip warn"><Icon name="camera" size={20} /><span><b>No diste permiso para usar la cámara.</b> Habilitalo en la configuración del navegador o escribí el código del cartel.</span></div>}
      {state === "nocamera" && <div className="card tip"><Icon name="camera" size={20} /><span>
        {window.isSecureContext ? "No encontramos una cámara en este dispositivo." : "El navegador solo permite usar la cámara en sitios seguros (https)."}
        {" "}Escribí el código que figura debajo del QR, o abrí la cámara de tu celular y apuntá al QR.</span></div>}

      <form className="card stack" onSubmit={submitCode}>
        <b>¿No te anda la cámara?</b>
        <small className="muted">Escribí el código de 6 caracteres que está debajo del QR (o el número que muestra la pantalla de la entrada).</small>
        <div className="row">
          <input className="input lg code-input" value={code} maxLength={8} autoCapitalize="characters" autoComplete="off"
            placeholder="ABC123" onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))} />
          <button className="btn primary lg" disabled={code.length < 6}>Ingresar</button>
        </div>
      </form>
      <button className="btn block" onClick={() => nav("/membresia")}><Icon name="qr" size={18} />Mostrar mi QR en recepción</button>
      <canvas ref={canvas} hidden />
    </div>
  );
}
