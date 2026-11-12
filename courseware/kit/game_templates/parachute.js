/* 接降落伞. Round: {options:[visual,...], answer:index}
 * Steer a basket to intercept a falling load. A fresh wave follows any miss.
 */
(function (T) {
  const C = T.colors;
  const LAND_Y = 570;
  const flightX = (d, i) => d.centers[i] + 27 * Math.sin(d.age * 2.2 + i * 2);

  function wave(d) {
    d.y = 289;
    d.age = 0;
  }

  T.register('parachute', {
    controls: [['left', '←', '篮子向左'], ['right', '→', '篮子向右']],
    validate(r) {
      T.options(r, 2, 4);
      T.answer(r);
      for (const visual of [r.background, r.basket]) if (visual != null) T.validateVisual(visual);
      T.assert(r.speed == null || T.integer(r.speed, 70, 140), 'invalid falling speed');
      T.assert(r.catchRadius == null || T.integer(r.catchRadius, 64, 112), 'invalid basket radius');
    },
    reset(r, level) {
      const d = {x: 640, y: 0, rest: 0, age: 0, speed: r.speed ?? 94 + 16 * level,
        centers: r.options.map((_, i) => 1280 * (i + 0.5) / r.options.length)};
      wave(d);
      return d;
    },
    pilot(g, d, r, dt) {
      const remaining = Math.max(0, (LAND_Y - d.y) / d.speed);
      const predicted = d.centers[r.answer] + 27 * Math.sin((d.age + remaining) * 2.2 + r.answer * 2);
      T.point(g, predicted, 625, true);
    },
    update(g, d, r, dt) {
      const pointer = T.getInput(g).pointer;
      const horizontal = T.axis(g, 'x');
      const target = horizontal ? d.x + horizontal * 80 : pointer.active ? pointer.x : d.x;
      d.x += T.clamp(T.clamp(target, 96, 1184) - d.x, -500 * dt, 500 * dt);
      if (d.rest > 0) {
        d.rest = Math.max(0, d.rest - dt);
        if (!d.rest) wave(d);
        return;
      }
      d.y = Math.min(LAND_Y, d.y + d.speed * dt);
      d.age += dt;
      if (d.y < LAND_Y) return;
      const caught = d.centers.findIndex((_, i) => Math.abs(flightX(d, i) - d.x) <= (r.catchRadius ?? 80));
      if (caught === r.answer) {
        if (g.score) d.caught = caught;
        T.success(g, {x: d.x, y: LAND_Y});
      }
      else {
        T.hint(g);
        if (r.speed != null && g.levelMisses >= 2) d.speed = Math.max(66, r.speed * .76);
        d.rest = 1.15;
      }
    },
    draw(g, c, d, r) {
      T.world(c, C.sky, '#E0ECCD', 658);
      if (r.background) T.visual(c, r.background, 640, 360, 1280, 720);
      for (let i = 0; i < d.centers.length; i++) {
        const x = flightX(d, i), y = d.y;
        if (d.rest || d.caught === i) continue;
        c.beginPath();
        c.ellipse(x, y - 58, 62, 33, 0, Math.PI, 0);
        c.fillStyle = ['#EA9D5E', '#66ACAD', '#8CA5D4', '#B8A1C5'][i];
        c.fill();
        T.line(c, {x: x - 59, y: y - 58}, {x: x - 35, y: y - 18}, C.ink, 3);
        T.line(c, {x: x + 59, y: y - 58}, {x: x + 35, y: y - 18}, C.ink, 3);
        T.token(c, r.options[i], {x, y}, 148, 106);
      }
      if (r.basket) T.visual(c, r.basket, d.x, 627, 182, 126);
      else {
        T.box(c, d.x - 91, 620, 182, 42, '#B47948', 15);
        T.box(c, d.x - 95, 610, 190, 15, C.earth, 8, '#AE6C40');
        for (let i = -2; i <= 2; i++) T.line(c, {x: d.x + i * 30, y: 627}, {x: d.x + i * 30, y: 653}, '#DDAD7E', 5);
      }
      if (d.caught != null) T.token(c, r.options[d.caught], {x:d.x,y:597}, 132, 96);
    },
    player(d) { return T.area(d.x, 623, 186, 88); },
    target(d) {
      if (d.caught != null) return T.area(d.x, 597, 132, 96);
      const near = d.centers.reduce((best, _, i) =>
        Math.abs(flightX(d, i) - d.x) < Math.abs(flightX(d, best) - d.x) ? i : best, 0);
      return T.area(flightX(d, near), d.y - 24, 150, 148);
    }
  });
})(K.gameTemplates.tools);
