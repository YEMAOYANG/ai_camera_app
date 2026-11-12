/* 碰碰车. Round: {options:[visual,...], answer:index}
 * Steer from the lower lane to bump the matching car. Other cars bounce you back safely.
 */
(function (T) {
  const C = T.colors;
  const COLORS = ['#CD8DA0', '#87AEE3', '#DAB073', '#87BAA2'];
  const MIN_Y = 307, MAX_Y = 648;

  function blockedBy(a, b) {
    return Math.abs(a.x - b.x) <= 176 && Math.abs(a.y - b.y) <= 120;
  }

  function car(c, p, v, fill, player = false) {
    T.box(c, p.x - 88, p.y - 59, 176, 118, '#395B5D', 25);
    T.box(c, p.x - 84, p.y - 62, 168, 112, fill, 26, C.ink);
    T.box(c, p.x - 77, p.y - 53, 154, 91, player ? C.sky : C.paper, 18, C.line);
    if (v != null) T.visual(c, v, p.x, p.y - 7, 152, 88);
    for (const x of [-64, 64]) T.circle(c, p.x + x, p.y + 42, 6, C.paper);
  }

  T.register('bumper', {
    validate(r) {
      T.options(r, 2, 4);
      T.answer(r);
      if (r.player != null) T.validateVisual(r.player);
    },
    reset(r, level) {
      return {me: {x: 640, y: MAX_Y}, age: 0, level, bump: 0, bounceTo: null,
        cars: r.options.map((_, i) => {
          const base = 1280 * (i + 0.5) / r.options.length;
          return {base, x: base, y: 377};
        })};
    },
    pilot(g, d, r) {
      const target = d.cars[r.answer];
      const inLane = Math.abs(d.me.x - target.base) < 45;
      T.point(g, inLane ? target.x : target.base, inLane ? target.y : MAX_Y, true);
    },
    update(g, d, r, dt) {
      d.age += dt;
      for (let i = 0; i < d.cars.length; i++) {
        const p = d.cars[i];
        p.x = p.base + (38 + d.level * 8) * Math.sin(d.age * 1.6 + i * 1.8);
        p.y = 377 + 54 * Math.sin(d.age * (1.2 + d.level * 0.3) + i * 2.7);
      }
      if (d.bump > 0) {
        d.bump = Math.max(0, d.bump - dt);
        T.move(d.me, d.bounceTo, 390, dt);
        return;
      }
      const p = T.getInput(g).pointer;
      const dx = T.axis(g, 'x'), dy = T.axis(g, 'y');
      const target = dx || dy ? {x: d.me.x + dx * 120, y: d.me.y + dy * 120} : p.active ? p : d.me;
      const before = {...d.me};
      T.move(d.me, {x: T.clamp(target.x, 92, 1188), y: T.clamp(target.y, MIN_Y, MAX_Y)}, 425, dt);
      const i = d.cars.findIndex(p => blockedBy(p, d.me));
      if (i >= 0) Object.assign(d.me, before);
      if (i === r.answer) T.success(g, d.me);
      else if (i >= 0) {
        const opponent = d.cars[i];
        const dx = d.me.x - opponent.x, dy = d.me.y - opponent.y;
        const gap = Math.max(1, Math.hypot(dx, dy));
        d.bounceTo = {x: T.clamp(d.me.x + dx * 160 / gap, 92, 1188),
          y: T.clamp(d.me.y + dy * 160 / gap, MIN_Y, MAX_Y)};
        d.bump = 0.7;
        T.hint(g);
        K.sfx.pop();
      }
    },
    draw(g, c, d, r) {
      T.world(c, '#EFF5EB');
      T.box(c, 36, 241, 1208, 459, '#D4E5DF', 53, '#87B2AB');
      c.save();
      c.setLineDash([18, 17]);
      T.line(c, {x: 88, y: 562}, {x: 1192, y: 562}, '#92B6AF', 5);
      c.restore();
      car(c, d.me, r.player ?? null, '#49A595', true);
      for (let i = 0; i < d.cars.length; i++) {
        const p = d.cars[i];
        if (p.x > 0) car(c, p, r.options[i], COLORS[i]);
      }
    },
    player(d) { return T.area(d.me.x, d.me.y, 176, 124); },
    target(d) {
      const closest = d.cars.reduce((a, b) => T.distance(a, d.me) < T.distance(b, d.me) ? a : b);
      return T.area(closest.x, closest.y, 176, 124);
    }
  });
})(K.gameTemplates.tools);
