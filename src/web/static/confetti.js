// Owner: Teammate 1 (Game, scenes, widgets)
// Confetti when the bomb is defused: one full-screen canvas, removed when the last piece
// falls off the screen. No library (no build step, spec §2).
//
// Reduced motion: no confetti at all. The "Defused" report already says the result.

const COLORS = ["#f2c230", "#4ade80", "#3f6fe6", "#ff5a4a", "#ecebe6", "#ffb43c"];
const PIECES = 160;
const MAX_MS = 6000;  // a hard stop, even if a background tab paints slowly

export function launchConfetti() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  document.querySelector("canvas.confetti")?.remove();
  const canvas = document.createElement("canvas");
  canvas.className = "confetti";
  canvas.setAttribute("aria-hidden", "true");
  document.body.append(canvas);
  const g = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const size = () => {
    canvas.width = innerWidth * dpr;
    canvas.height = innerHeight * dpr;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  size();
  window.addEventListener("resize", size);

  // Two bursts from the bottom corners, aimed up and in, like party poppers. The height a
  // piece reaches grows with speed squared, so speed scales with the square root of the
  // window height: the burst reaches the same share of a tall screen as of a small one.
  const reach = Math.sqrt(innerHeight / 720);
  const pieces = Array.from({ length: PIECES }, (_, k) => {
    const left = k % 2 === 0;
    const angle = (left ? -60 : -120) * (Math.PI / 180) + (Math.random() - 0.5) * 0.9;
    const speed = (11 + Math.random() * 9) * reach;
    return {
      x: left ? 0 : innerWidth, y: innerHeight,
      vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
      w: 6 + Math.random() * 6, h: 8 + Math.random() * 10,
      rot: Math.random() * Math.PI, spin: (Math.random() - 0.5) * 0.3,
      tilt: Math.random() * Math.PI, color: COLORS[k % COLORS.length],
    };
  });

  const start = performance.now();
  let last = start;
  const frame = (now) => {
    const dt = Math.min(2, (now - last) / 16.7);  // in 60 fps frames; capped after a stall
    last = now;
    g.clearRect(0, 0, innerWidth, innerHeight);
    let alive = 0;
    for (const p of pieces) {
      p.vy += 0.35 * dt;   // gravity
      p.vx *= 0.985 ** dt; // air drag
      p.vy *= 0.985 ** dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.rot += p.spin * dt;
      p.tilt += 0.12 * dt;
      if (p.y > innerHeight + 40) continue;
      alive++;
      g.save();
      g.translate(p.x, p.y);
      g.rotate(p.rot);
      g.scale(1, Math.cos(p.tilt));  // the flutter: a paper piece turning over
      g.fillStyle = p.color;
      g.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
      g.restore();
    }
    if (alive && now - start < MAX_MS) requestAnimationFrame(frame);
    else {
      window.removeEventListener("resize", size);
      canvas.remove();
    }
  };
  requestAnimationFrame(frame);
}
