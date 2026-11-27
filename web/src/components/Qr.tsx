import qrcode from "qrcode-generator";
import { useMemo } from "react";

/** A QR code as plain SVG rects (no innerHTML, no canvas). */
export function Qr({ value, label }: { value: string; label: string }) {
  const { n, path } = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(value.toUpperCase(), "Alphanumeric"); // BOLT 11 is case-insensitive: denser QR
    qr.make();
    const n = qr.getModuleCount();
    let d = "";
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) d += `M${c} ${r}h1v1h-1z`;
    return { n, path: d };
  }, [value]);
  return (
    <svg className="qr" viewBox={`-4 -4 ${n + 8} ${n + 8}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect x="-4" y="-4" width={n + 8} height={n + 8} fill="#fff" />
      <path d={path} fill="#000" />
    </svg>
  );
}
