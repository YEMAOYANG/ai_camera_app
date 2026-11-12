/* 钓鱼. Round: {options:[visual,...], matches:[indices]}
 * Sail horizontally and cast. Only the first fish actually touched by the hook is reeled in.
 */
(function (T) {
  const C = T.colors;
  const SURFACE = 286, CAST_Y = 244, BOTTOM = 683;

  function fishX(d, i) {
    const x = d.fish[i].center + (34 + d.level * 4) * Math.sin(d.age * (1.45 + d.level * 0.18) + i * 2);
    return T.clamp(x, 100, 1180);
  }

  T.register('fishing', {
    validate(r) {
      T.options(r, 2, 5);
      T.indices(r.matches, r.options.length, 'matches');
      T.assert(r.matches.length < r.options.length, 'fishing needs at least one distractor');
    },
    reset(r, level) {
      return {x: 640, y: SURFACE, hookY: 0, age: 0, level, cast: 0, haul: -1, got: new Set(),
        fish: r.options.map((_, i) => ({center: 1280 * (i + 0.5) / r.options.length, y: [418, 585, 484][i % 3]}))};
    },
    pilot(g, d, r) {
      if (d.cast) return;
      const target = r.matches.find(i => !d.got.has(i));
      const x = d.fish[target].center;
      T.point(g, x, CAST_Y, false, Math.abs(x - d.x) < 10);
    },
    update(g, d, r, dt) {
      d.age += dt;
      if (d.cast === 1) {
        d.hookY += 480 * dt;
        const i = d.fish.findIndex((f, i) => !d.got.has(i) &&
          Math.abs(d.hookY - f.y) <= 30 && Math.abs(d.x - fishX(d, i)) <= 72);
        if (i >= 0 || d.hookY >= BOTTOM) {
          d.haul = i;
          d.cast = -1;
        }
        return;
      }
      if (d.cast === -1) {
        d.hookY -= 580 * dt;
        if (d.hookY > SURFACE) return;
        d.cast = 0;
        if (r.matches.includes(d.haul)) {
          d.got.add(d.haul);
          g.sparkle(d.x, SURFACE);
          K.sfx.ok();
          if (d.got.size === r.matches.length) T.success(g, {x: d.x, y: SURFACE});
        } else {
          T.hint(g);
        }
        d.haul = -1;
        return;
      }
      const input = T.getInput(g);
      const dx = T.axis(g, 'x');
      const target = dx ? d.x + dx * 80 : input.pointer.active ? input.pointer.x : d.x;
      d.x += T.clamp(T.clamp(target, 87, 1193) - d.x, -500 * dt, 500 * dt);
      if (input.taps.some(p => p.key || p.y <= SURFACE + 45)) {
        d.hookY = SURFACE;
        d.cast = 1;
        K.sfx.drop();
      }
    },
    draw(g, c, d, r) {
      T.world(c, C.sky, '#8DCDD6', SURFACE);
      for (const y of [SURFACE + 2, 350, 540, 679]) {
        T.line(c, {x: 0, y}, {x: 1280, y}, '#AFDEE2', 6);
      }
      function drawFish(i, x, y) {
        c.beginPath();
        c.moveTo(x - 65, y);
        c.lineTo(x - 98, y - 28);
        c.lineTo(x - 98, y + 28);
        c.closePath();
        c.fillStyle = '#2A8B91';
        c.fill();
        T.token(c, r.options[i], {x, y}, 153, 92);
      }
      for (let i = 0; i < d.fish.length; i++) {
        if (!d.got.has(i) && d.haul !== i) drawFish(i, fishX(d, i), d.fish[i].y);
      }
      T.box(c, d.x - 78, SURFACE - 26, 156, 46, '#AD734B', 20, '#7D553A');
      T.box(c, d.x - 29, SURFACE - 55, 58, 32, C.paper, 10, C.line);
      if (d.cast) {
        T.line(c, {x: d.x, y: SURFACE - 23}, {x: d.x, y: d.hookY}, C.ink, 4);
        T.circle(c, d.x, d.hookY, 8, C.accent);
        if (d.haul >= 0) drawFish(d.haul, d.x, Math.min(d.hookY + 30, 656));
      }
    },
    player(d) { return T.area(d.x, SURFACE - 12, 160, 100); },
    target(d) {
      const target = d.fish.reduce((best, f, i) => !d.got.has(i) &&
        (best < 0 || Math.abs(fishX(d, i) - d.x) < Math.abs(fishX(d, best) - d.x)) ? i : best, -1);
      return target < 0 ? null : T.area(fishX(d, target), d.fish[target].y, 153, 92);
    }
  });
})(K.gameTemplates.tools);
