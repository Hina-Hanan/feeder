/** Host-side game simulation (browser). */
const Sim = (() => {
  const W = 1152, H = 648;
  const TARGET = 5, BASE_HEAD = 70, GROW = 22, MIN_HEAD = 40;
  const SPEED = 280, RESPAWN_MIN_DIST = 120, FOOD_SEP = 100;
  const FEET_Y_MIN = 280, FEET_Y_MAX = H - 55, EAT_FEET_RADIUS = 58;
  const FOOD_RESPAWN_DELAY = 0.35;
  const COLORS = ["#f0c896", "#f0aa78", "#a0c8f0", "#c8f0a0"];

  function dist(ax, ay, bx, by) {
    return Math.hypot(ax - bx, ay - by);
  }

  class Room {
    constructor() {
      this.players = [];
      this.inputs = {};
      this.started = false;
      this.winner_slot = null;
    }

    addPlayer(name, fav, face = null) {
      if (this.started || this.players.length >= 4) return null;
      const slot = this.players.length;
      const p = {
        slot, name: (name || `Player${slot + 1}`).slice(0, 16), fav, face,
        isBot: false,
        x: 100 + Math.random() * (W - 200),
        y: 250 + Math.random() * (H - 290),
        count: 0, facing: 1, moving: false, burst: false, flash: 0,
        meal: null, meal_timer: 0, last_meal_pos: null, run_t: 0,
        color: COLORS[slot % COLORS.length],
      };
      this.players.push(p);
      this.inputs[slot] = [0, 0];
      return p;
    }

    headSize(p) { return Math.max(MIN_HEAD, BASE_HEAD + GROW * p.count); }

    otherMeals(skip) {
      return this.players.filter(p => p.slot !== skip && p.meal).map(p => p.meal.pos);
    }

    spawnMeal(p, avoid) {
      const others = this.otherMeals(p.slot);
      for (let i = 0; i < 160; i++) {
        const x = 70 + Math.random() * (W - 140);
        const y = FEET_Y_MIN + Math.random() * (FEET_Y_MAX - FEET_Y_MIN);
        if (avoid && dist(x, y, avoid[0], avoid[1]) < RESPAWN_MIN_DIST) continue;
        if (others.some(([ox, oy]) => dist(x, y, ox, oy) < FOOD_SEP)) continue;
        return { name: p.fav, pos: [x, y], owner: p.slot };
      }
      return { name: p.fav, pos: [W / 2, H / 2], owner: p.slot };
    }

    initMeals() {
      this.players.forEach(p => { p.meal = null; p.meal_timer = 0; p.last_meal_pos = null; });
      this.players.forEach(p => { p.meal = this.spawnMeal(p); });
    }

    ensureMeals() {
      this.players.forEach(p => {
        if (p.burst) { p.meal = null; return; }
        if (!p.meal && p.meal_timer <= 0) p.meal = this.spawnMeal(p, p.last_meal_pos);
      });
    }

    tryEat(p) {
      const m = p.meal;
      if (!m || m.owner !== p.slot) return;
      if (dist(p.x, p.y, m.pos[0], m.pos[1]) > EAT_FEET_RADIUS) return;
      p.count++;
      p.last_meal_pos = m.pos;
      p.meal = null;
      p.meal_timer = FOOD_RESPAWN_DELAY;
      if (p.count >= TARGET) { p.burst = true; this.winner_slot = p.slot; }
    }

    step(dt) {
      if (this.winner_slot != null) return;
      this.ensureMeals();
      this.players.forEach(p => {
        if (p.burst) return;
        let mx = 0;
        let my = 0;
        if (p.isBot) {
          if (p.meal) {
            const dx = p.meal.pos[0] - p.x;
            const dy = p.meal.pos[1] - p.y;
            const d = Math.hypot(dx, dy);
            if (d > EAT_FEET_RADIUS && d > 1) {
              mx = dx / d;
              my = dy / d;
            }
          }
        } else {
          [mx, my] = this.inputs[p.slot] || [0, 0];
        }
        const len = Math.hypot(mx, my);
        p.moving = len > 0;
        if (len > 0) {
          p.x += (mx / len) * SPEED * dt;
          p.y += (my / len) * SPEED * dt;
          if (mx) p.facing = mx > 0 ? 1 : -1;
        }
        p.x = Math.max(30, Math.min(W - 30, p.x));
        p.y = Math.max(FEET_Y_MIN - 20, Math.min(H - 30, p.y));
        p.run_t = p.moving ? p.run_t + dt * 14 : p.run_t * 0.9;
        p.flash = Math.max(0, p.flash - dt);
        p.meal_timer = Math.max(0, p.meal_timer - dt);
      });
      this.players.forEach(p => this.tryEat(p));
    }

    playerList() {
      return this.players.map(p => ({ slot: p.slot, name: p.name, fav: p.fav }));
    }

    publicState() {
      return {
        started: this.started,
        winner_slot: this.winner_slot,
        players: this.playerList(),
        runners: this.players.map(p => ({
          slot: p.slot, name: p.name, fav: p.fav,
          x: p.x, y: p.y, count: p.count, facing: p.facing,
          moving: p.moving, burst: p.burst, flash: p.flash, run_t: p.run_t,
          head_size: this.headSize(p), color: p.color, meal: p.meal, face: p.face,
        })),
      };
    }

    start() {
      if (!this.players.length) return false;
      this.started = true;
      this.winner_slot = null;
      this.players.forEach(p => {
        p.count = 0; p.burst = false;
        p.x = 100 + Math.random() * (W - 200);
        p.y = 250 + Math.random() * (H - 290);
      });
      this.initMeals();
      return true;
    }
  }

  return { Room, W, H };
})();
