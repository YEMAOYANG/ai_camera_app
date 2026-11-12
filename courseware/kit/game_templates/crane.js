/* 吊车. Round: {cars:[visual,...], cargo:visual, drop:[indices], engine?:'left'|'right'}
 * The claw sweeps the track. Press to drop onto the required car(s), indexed from the engine.
 */
(function (T) {
  const C = T.colors;
  const RAIL = 281, CAR_Y = 575, CLAW_Y = 354;
  const STEP = 96;

  function carX(d, index) {
    return 640 + d.side * (STEP * (index - (d.count - 1) / 2));
  }

  function getCar(d, x) {
    for (let i = 0; i < d.count; i++) if (Math.abs(x - carX(d, i)) <= 46) return i;
    return -1;
  }

  T.register('crane', {
    validate(r) {
      T.options(r, 2, 10, 'cars');
      T.indices(r.drop, r.cars.length, 'drop');
      T.validateVisual(r.cargo);
      T.assert(r.engine == null || ['left', 'right'].includes(r.engine), 'engine must be left or right');
    },
    reset(r, level) {
      return {count: r.cars.length, side: r.engine === 'right' ? -1 : 1, x: 128,
        dir: 1, speed: 250 + level * 42, fall: 0, landed: new Set()};
    },
    pilot(g, d, r) {
      if (!d.fall && r.drop.some(i => !d.landed.has(i) && Math.abs(d.x - carX(d, i)) < 23)) {
        T.point(g, d.x, CLAW_Y, false, true);
      }
    },
    update(g, d, r, dt) {
      if (d.fall > 0) {
        d.fall += dt;
        if (d.fall >= 0.52) {
          d.fall = 0;
          const car = getCar(d, d.x);
          if (!r.drop.includes(car) || d.landed.has(car)) T.hint(g);
          else {
            d.landed.add(car);
            K.sfx.ok();
            g.burst(d.x, CAR_Y - 45, {n: 7});
            if (g.demoAction?.()) return;
            if (d.landed.size === r.drop.length) T.success(g, {x: d.x, y: CAR_Y});
          }
        }
        return;
      }
      if (T.pressed(g)) {
        d.fall = 0.001;
        K.sfx.drop();
      } else if (dt > 0) {
        d.x += d.dir * d.speed * dt;
        if (d.dir < 0 ? d.x <= 128 : d.x >= 1152) {
          d.dir *= -1;
          d.x = T.clamp(d.x, 128, 1152);
        }
      }
    },
    draw(g, c, d, r) {
      T.world(c, '#EBF4EE', '#CBDDCC', 652);
      T.line(c, {x: 106, y: RAIL}, {x: 1174, y: RAIL}, C.ink, 12);
      T.line(c, {x: 42, y: 646}, {x: 1238, y: 646}, C.ink, 8);
      const engine = carX(d, 0) - d.side * 110;
      T.box(c, engine - 51, CAR_Y - 33, 102, 76, C.accent);
      T.box(c, engine + d.side * 11 - 28, CAR_Y - 69, 57, 62, C.accent, 12);
      T.box(c, engine + d.side * 11 - 16, CAR_Y - 57, 32, 24, C.sky, 8);
      for (let i = 0; i < d.count; i++) {
        const x = carX(d, i);
        T.token(c, r.cars[i], {x, y: CAR_Y}, 88, 94, d.landed.has(i) ? C.mint : C.paper);
        for (const dx of [-25, 25]) T.circle(c, x + dx, CAR_Y + 56, 11, C.ink);
        if (d.landed.has(i)) T.visual(c, r.cargo, x, CAR_Y - 68, 68, 52);
      }
      T.box(c, d.x - 52, RAIL - 26, 104, 52, C.amber);
      T.line(c, {x: d.x, y: RAIL}, {x: d.x, y: CLAW_Y}, C.ink, 6);
      T.line(c, {x: d.x, y: CLAW_Y + 43}, {x: d.x, y: CAR_Y + 45}, '#ACC7C2', 4);
      if (!d.fall) T.token(c, r.cargo, {x: d.x, y: CLAW_Y}, 90, 82);
      else T.token(c, r.cargo, {x: d.x, y: CLAW_Y + (CAR_Y - CLAW_Y - 65) * (d.fall / 0.52) ** 2}, 90, 82);
    },
    player(d) { return T.area(d.x, CLAW_Y, 100, 96); },
    target(d) {
      const car = getCar(d, d.x);
      return T.area(car < 0 ? d.x : carX(d, car), CAR_Y, 90, 104);
    }
  });
})(K.gameTemplates.tools);
