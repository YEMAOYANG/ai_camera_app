/* 套圈. Round: {targets:[visual,...], rings:number, matches?:[indices]}
 * Aim and release to throw. Each moving target can take one ring.
 * Omit matches for one-to-one correspondence with any distinct targets.
 */
(function (T) {
  const C = T.colors;
  const LAUNCH = {x: 640, y: 672}, FLIGHT = 0.62;

  function position(d, index, age = d.age) {
    const count = d.count;
    const row = Math.floor(index / 4);
    const inRow = Math.min(4, count - row * 4);
    return {x: (index % 4 + 0.5) * (1280 / inRow) + 40 * Math.sin(age * (1.45 + d.level * 0.4) + index * 1.9),
      y: (count > 8 ? [317, 446, 575][row] : count > 4 ? [345, 515][row] : 440) +
        (count > 8 ? 10 : 18) * Math.sin(age * 1.95 + index * 1.1)};
  }

  function drawRing(c, p, color) {
    c.beginPath();
    c.ellipse(p.x, p.y, 45, 24, 0, 0, Math.PI * 2);
    c.lineWidth = 10;
    c.strokeStyle = color;
    c.stroke();
  }

  T.register('ring', {
    validate(r) {
      T.options(r, 2, 10, 'targets');
      T.assert(T.integer(r.rings, 1, r.targets.length), 'invalid ring supply');
      if (r.matches != null) {
        T.indices(r.matches, r.targets.length, 'matches');
        T.assert(r.matches.length === r.rings, 'ring supply must match the required targets');
      }
    },
    reset(r, level) {
      return {count: r.targets.length, level, age: 0, flight: 0, aim: null, thrown: null, got: new Set()};
    },
    pilot(g, d, r, dt) {
      if (d.flight) return;
      const candidates = r.matches || r.targets.map((_, i) => i);
      const i = candidates.find(i => !d.got.has(i));
      const aim = position(d, i, d.age + FLIGHT + dt);
      T.point(g, aim.x, aim.y, !d.aim);
    },
    update(g, d, r, dt) {
      d.age += dt;
      if (d.flight > 0) {
        d.flight += dt;
        if (d.flight >= FLIGHT) {
          let target = -1, best = 50;
          for (let i = 0; i < d.count; i++) {
            const gap = T.distance(d.thrown, position(d, i));
            if (gap <= best) {
              target = i;
              best = gap;
            }
          }
          d.flight = 0;
          if (target < 0 || d.got.has(target) || (r.matches && !r.matches.includes(target))) T.hint(g);
          else {
            d.got.add(target);
            K.sfx.pop();
            g.sparkle(d.thrown.x, d.thrown.y);
            if (d.got.size === r.rings) T.success(g, d.thrown);
          }
        }
        return;
      }
      const p = T.getInput(g).pointer;
      if (p.down) {
        d.aim = {x: T.clamp(p.x, 47, 1233), y: T.clamp(p.y, 262, 593)};
      } else if (d.aim) {
        d.thrown = d.aim;
        d.aim = null;
        d.flight = 0.001;
        K.sfx.whoosh();
      }
    },
    draw(g, c, d, r) {
      T.world(c, '#BAE1DD', '#9BD0C9', 611);
      for (const y of [256, 423, 578]) T.line(c, {x: 55, y}, {x: 1225, y}, '#A9D4CE', 5);
      for (let i = 0; i < d.count; i++) {
        const p = position(d, i);
        T.token(c, r.targets[i], p, 139, 94, d.got.has(i) ? C.mint : C.paper);
        if (d.got.has(i)) drawRing(c, {x: p.x, y: p.y + 32}, C.accent);
      }
      const n = r.rings - d.got.size;
      for (let i = 0; i < n; i++) drawRing(c, {x: LAUNCH.x + (i - (n - 1) / 2) * 96, y: LAUNCH.y}, '#D08552');
      if (d.aim) drawRing(c, d.aim, C.accent);
      if (d.flight) {
        const t = Math.min(1, d.flight / FLIGHT);
        drawRing(c, {x: LAUNCH.x + (d.thrown.x - LAUNCH.x) * t,
          y: LAUNCH.y + (d.thrown.y - LAUNCH.y) * t - 135 * Math.sin(t * Math.PI)}, '#D08552');
      }
    },
    player() { return T.area(LAUNCH.x, LAUNCH.y, 106, 96); },
    target(d) {
      const p = d.aim || d.thrown || position(d, 0);
      return T.area(p.x, p.y, 116, 94);
    }
  });
})(K.gameTemplates.tools);
