/** Winner head burst: fire, sparks, confetti, party poppers */
const WinFX = (() => {
  const POP_COLORS = ["#ff2d2d", "#ff8c00", "#ffee00", "#00e5ff", "#ff44cc", "#66ff66", "#ffffff"];

  let particles = [];
  let burstFlash = 0;
  let burstRing = 0;
  let firedFor = null;
  let origin = { x: 0, y: 0 };

  function reset() {
    particles = [];
    burstFlash = 0;
    burstRing = 0;
    firedFor = null;
  }

  function fxScale() {
    return (typeof window !== "undefined" && window.FTF_EMBEDDED) ? 0.5 : 1;
  }

  function spawn(winnerSlot, x, y) {
    if (firedFor === winnerSlot) return;
    firedFor = winnerSlot;
    origin = { x, y };
    burstFlash = 0.45;
    burstRing = 0;
    const k = fxScale();

    for (let i = 0; i < Math.max(20, Math.floor(55 * k)); i++) {
      const a = Math.random() * Math.PI * 2;
      const sp = 100 + Math.random() * 380;
      particles.push({
        kind: "fire",
        x, y,
        vx: Math.cos(a) * sp,
        vy: Math.sin(a) * sp - 40,
        life: 0.35 + Math.random() * 0.55,
        r: 6 + Math.random() * 22,
      });
    }
    for (let i = 0; i < Math.max(30, Math.floor(80 * k)); i++) {
      const a = Math.random() * Math.PI * 2;
      const sp = 200 + Math.random() * 550;
      particles.push({
        kind: "spark",
        x, y,
        vx: Math.cos(a) * sp,
        vy: Math.sin(a) * sp,
        life: 0.25 + Math.random() * 0.45,
        r: 2 + Math.random() * 4,
      });
    }
    for (let i = 0; i < Math.max(50, Math.floor(140 * k)); i++) {
      const a = Math.random() * Math.PI * 2;
      const sp = 120 + Math.random() * 420;
      particles.push({
        kind: "confetti",
        x, y,
        vx: Math.cos(a) * sp,
        vy: Math.sin(a) * sp - 80,
        life: 1.2 + Math.random() * 1.8,
        w: 6 + Math.random() * 8,
        h: 10 + Math.random() * 14,
        rot: Math.random() * Math.PI,
        vr: (Math.random() - 0.5) * 12,
        color: POP_COLORS[i % POP_COLORS.length],
      });
    }
    const poppers = Math.max(4, Math.floor(8 * k));
    const streamers = Math.max(8, Math.floor(18 * k));
    for (let b = 0; b < poppers; b++) {
      const a = -Math.PI / 2 + (Math.random() - 0.5) * 1.2;
      for (let j = 0; j < streamers; j++) {
        const spread = (Math.random() - 0.5) * 0.7;
        const sp = 280 + Math.random() * 320;
        particles.push({
          kind: "streamer",
          x, y,
          vx: Math.cos(a + spread) * sp,
          vy: Math.sin(a + spread) * sp,
          life: 0.9 + Math.random() * 0.8,
          color: POP_COLORS[(b + j) % POP_COLORS.length],
          len: 12 + Math.random() * 20,
        });
      }
    }
  }

  function update(dt) {
    if (burstFlash > 0) burstFlash -= dt;
    if (burstRing < 1) burstRing += dt * 2.2;

    particles.forEach(p => {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.life -= dt;
      if (p.kind === "fire") {
        p.vy -= 90 * dt;
        p.r += 28 * dt;
        p.vx *= 1 - dt * 0.8;
      } else if (p.kind === "spark") {
        p.vy += 180 * dt;
      } else if (p.kind === "confetti") {
        p.vy += 420 * dt;
        p.vx *= 1 - dt * 0.35;
        p.rot += p.vr * dt;
      } else if (p.kind === "streamer") {
        p.vy += 320 * dt;
        p.vx *= 1 - dt * 0.2;
      }
    });
    particles = particles.filter(p => p.life > 0);
  }

  function draw(ctx) {
    const { x, y } = origin;
    if (burstFlash > 0) {
      const g = ctx.createRadialGradient(x, y, 0, x, y, 120 + burstRing * 90);
      g.addColorStop(0, `rgba(255, 255, 220, ${burstFlash * 1.2})`);
      g.addColorStop(0.35, `rgba(255, 120, 20, ${burstFlash * 0.9})`);
      g.addColorStop(1, "rgba(255, 40, 0, 0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(x, y, 140 + burstRing * 100, 0, Math.PI * 2);
      ctx.fill();
    }
    if (burstRing < 0.85) {
      ctx.strokeStyle = `rgba(255, 200, 50, ${0.7 * (1 - burstRing)})`;
      ctx.lineWidth = 10;
      ctx.beginPath();
      ctx.arc(x, y, 30 + burstRing * 110, 0, Math.PI * 2);
      ctx.stroke();
    }

    particles.forEach(p => {
      const a = Math.max(0, Math.min(1, p.life * 2));
      if (p.kind === "fire") {
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
        g.addColorStop(0, `rgba(255, 255, 200, ${a})`);
        g.addColorStop(0.4, `rgba(255, 140, 0, ${a * 0.85})`);
        g.addColorStop(1, "rgba(180, 0, 0, 0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      } else if (p.kind === "spark") {
        ctx.fillStyle = `rgba(255, 240, 120, ${a})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      } else if (p.kind === "confetti") {
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = a;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      } else if (p.kind === "streamer") {
        ctx.strokeStyle = p.color;
        ctx.globalAlpha = a;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(p.x - p.vx * 0.04, p.y - p.vy * 0.04 - p.len);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    });
    ctx.globalAlpha = 1;
  }

  return { spawn, update, draw, reset };
})();
