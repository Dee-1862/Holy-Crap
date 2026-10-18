import { TYPES, type TypeKey } from "./data";

// Small seeded generator so each specimen draws the same picture every time.
function seeded(seed: number) {
  let s = seed >>> 0;
  return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;
}

function shade(hex: string, amt: number) {
  const n = parseInt(hex.slice(1), 16);
  const f = (v: number) => Math.max(0, Math.min(255, v + amt));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`;
}

// Draws a synthetic placeholder specimen with an optional attention overlay.
// Replace with the stored snapshot and a Grad-CAM image from the backend.
export function drawSpecimen(canvas: HTMLCanvasElement, type: TypeKey, region: [number, number], heat: boolean, seedKey: string) {
  const c = canvas.getContext("2d");
  if (!c) return;
  const w = canvas.width;
  const h = canvas.height;
  const rnd = seeded(seedKey.split("").reduce((a, ch) => a * 31 + ch.charCodeAt(0), 7));

  c.fillStyle = "#1b1712";
  c.fillRect(0, 0, w, h);
  for (let i = 0; i < 520; i++) {
    c.strokeStyle = `rgba(${150 + rnd() * 70},${120 + rnd() * 50},${70 + rnd() * 40},${0.14 + rnd() * 0.2})`;
    c.lineWidth = 1 + rnd() * 1.4;
    c.beginPath();
    const x = rnd() * w;
    const y = rnd() * h;
    const a = rnd() * 6.28;
    const l = 6 + rnd() * 16;
    c.moveTo(x, y);
    c.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l);
    c.stroke();
  }

  const cx = w * region[0];
  const cy = h * region[1];
  const base = TYPES[type].color;
  const wet = type === "healthy" ? 1 : 1.5;
  c.save();
  c.translate(cx, cy);
  c.fillStyle = base;
  c.beginPath();
  c.ellipse(0, 0, 52 * wet, 38 * wet, 0.3, 0, 6.28);
  c.fill();
  c.fillStyle = shade(base, -18);
  c.beginPath();
  c.ellipse(-6, 6, 36 * wet, 24 * wet, 0.3, 0, 6.28);
  c.fill();
  if (type === "healthy") {
    c.fillStyle = "#efe9de";
    c.beginPath();
    c.ellipse(14, -10, 20, 14, 0.3, 0, 6.28);
    c.fill();
  }
  if (type === "coccidiosis") {
    c.strokeStyle = "#a3231c";
    c.lineWidth = 3;
    for (let i = 0; i < 5; i++) {
      c.beginPath();
      c.moveTo(-30 + i * 12, -10);
      c.quadraticCurveTo(-10 + i * 8, 14, -26 + i * 14, 28);
      c.stroke();
    }
  }
  if (type === "salmonella") {
    c.fillStyle = "rgba(255,248,210,.55)";
    for (let i = 0; i < 16; i++) {
      c.beginPath();
      c.arc((rnd() - 0.5) * 90, (rnd() - 0.5) * 60, 2 + rnd() * 4, 0, 6.28);
      c.fill();
    }
  }
  if (type === "ncd") {
    c.fillStyle = "rgba(190,255,150,.25)";
    c.beginPath();
    c.ellipse(-8, 4, 44, 28, 0, 0, 6.28);
    c.fill();
  }
  c.restore();

  if (heat) {
    const g = c.createRadialGradient(cx, cy + 6, 4, cx, cy + 6, 82);
    g.addColorStop(0, "rgba(255,196,64,.8)");
    g.addColorStop(0.45, "rgba(255,150,70,.42)");
    g.addColorStop(1, "rgba(255,150,70,0)");
    c.fillStyle = g;
    c.fillRect(0, 0, w, h);
    c.strokeStyle = "#ffffff";
    c.lineWidth = 1.5;
    c.setLineDash([5, 4]);
    c.strokeRect(cx - 74, cy - 54, 148, 108);
    c.setLineDash([]);
  }
}
