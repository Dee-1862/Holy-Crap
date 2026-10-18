// Draws a synthetic placeholder specimen image with an optional attention overlay.
function seeded(seed) { let s = seed >>> 0; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; }
/* ---------- specimen drawing (placeholder illustration) ---------- */
function drawSpecimen(canvas, type, region, heat, seedKey) {
  const w = canvas.width, h = canvas.height, c = canvas.getContext("2d");
  const rnd = seeded(seedKey.split("").reduce((a, ch) => a * 31 + ch.charCodeAt(0), 7));
  c.fillStyle = "#1b1712"; c.fillRect(0, 0, w, h);                         // litter
  for (let i = 0; i < 520; i++) {
    c.strokeStyle = `rgba(${150 + rnd() * 70},${120 + rnd() * 50},${70 + rnd() * 40},${.14 + rnd() * .2})`;
    c.lineWidth = 1 + rnd() * 1.4; c.beginPath();
    const x = rnd() * w, y = rnd() * h, a = rnd() * 6.28, l = 6 + rnd() * 16;
    c.moveTo(x, y); c.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l); c.stroke();
  }
  const cx = w * region[0], cy = h * region[1], base = TYPES[type].color;
  const wet = type === "healthy" ? 1 : 1.5;
  c.save(); c.translate(cx, cy);
  c.fillStyle = base; c.beginPath();
  c.ellipse(0, 0, 52 * wet, 38 * wet, .3, 0, 6.28); c.fill();
  c.fillStyle = shade(base, -18); c.beginPath(); c.ellipse(-6, 6, 36 * wet, 24 * wet, .3, 0, 6.28); c.fill();
  if (type === "healthy") { c.fillStyle = "#efe9de"; c.beginPath(); c.ellipse(14, -10, 20, 14, .3, 0, 6.28); c.fill(); }
  if (type === "coccidiosis") { c.strokeStyle = "#a3231c"; c.lineWidth = 3; for (let i = 0; i < 5; i++) { c.beginPath(); c.moveTo(-30 + i * 12, -10); c.quadraticCurveTo(-10 + i * 8, 14, -26 + i * 14, 28); c.stroke(); } }
  if (type === "salmonella") { c.fillStyle = "rgba(255,248,210,.55)"; for (let i = 0; i < 16; i++) { c.beginPath(); c.arc((rnd() - .5) * 90, (rnd() - .5) * 60, 2 + rnd() * 4, 0, 6.28); c.fill(); } }
  if (type === "ncd") { c.fillStyle = "rgba(190,255,150,.25)"; c.beginPath(); c.ellipse(-8, 4, 44, 28, 0, 0, 6.28); c.fill(); }
  c.restore();
  if (heat) {                                                              // explainability overlay
    const g = c.createRadialGradient(cx, cy + 6, 4, cx, cy + 6, 82);
    g.addColorStop(0, "rgba(255,106,26,.85)"); g.addColorStop(.45, "rgba(255,150,40,.45)"); g.addColorStop(1, "rgba(255,106,26,0)");
    c.fillStyle = g; c.fillRect(0, 0, w, h);
    c.strokeStyle = "#2ab7c9"; c.lineWidth = 1.5; c.setLineDash([5, 4]);
    c.strokeRect(cx - 74, cy - 54, 148, 108); c.setLineDash([]);
  }
}
function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const f = (v) => Math.max(0, Math.min(255, v + amt));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`;
}

