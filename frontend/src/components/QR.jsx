import qrcode from "qrcode-generator";
import { useMemo } from "react";

export default function QR({ value, size = 220 }) {
  const svg = useMemo(() => {
    const q = qrcode(0, "M");
    q.addData(value || "-");
    q.make();
    return q.createSvgTag({ cellSize: 8, margin: 2, scalable: true });
  }, [value]);
  return <div className="qr" style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: svg }} />;
}
