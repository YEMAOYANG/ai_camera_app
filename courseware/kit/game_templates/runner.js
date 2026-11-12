/* 跑酷. Round: {collect, track:[{value, visual?, airborne?:true}]}
 * Jump to take high groups or let low groups pass. Finish with the exact quantity.
 */
(function (T) {
  const RUNNER_X = 270, GROUND = 615, FLIGHT = 0.88;
  const C = T.colors;

  function canCollect(track, index, need) {
    const totals = new Set([0]);
    for (const item of track.slice(index)) {
      for (const total of [...totals]) {
        if (total + item.value <= need) totals.add(total + item.value);
      }
    }
    return totals.has(need);
  }

  function take(d, r) {
    const item = r.track[d.index];
    const rest = r.collect - d.count;
    return !canCollect(r.track, d.index + 1, rest);
  }

  T.register('runner', {
    validate(r) {
      T.assert(T.integer(r.collect, 1, 24) && Array.isArray(r.track) &&
        T.integer(r.track.length, 2, 10), 'runner needs collect and 2–10 track groups');
      for (const item of r.track) {
        T.assert(item && T.integer(item.value, 1, 24), 'invalid runner group');
        T.validateVisual(item.visual ?? {count: item.value});
      }
      T.assert(r.track.reduce((n, i) => n + i.value, 0) > r.collect &&
        canCollect(r.track, 0, r.collect), 'runner needs a reachable exact total and surplus groups to dodge');
    },
    reset(r, level) {
      return {index: 0, count: 0, x: 1040, jump: 0, retry: 0,
        speed: 355 + level * 35, airborne: !!r.track[0].airborne};
    },
    pilot(g, d, r, dt) {
      if (d.retry || d.jump || d.index >= r.track.length) return;
      const item = r.track[d.index];
      if (take(d, r) === !!item.airborne && d.x - RUNNER_X <= d.speed * (0.43 + dt)) {
        T.point(g, RUNNER_X, 620, false, true);
      }
    },
    update(g, d, r, dt) {
      if (d.retry > 0) {
        d.retry = Math.max(0, d.retry - dt);
        if (!d.retry) {
          d.index = 0;
          d.x = 1040;
          d.count = 0;
          d.jump = 0;
          d.airborne = !!r.track[0].airborne;
        }
        return;
      }
      if (T.pressed(g) && d.jump === 0) {
        d.jump = FLIGHT;
        K.sfx.jump();
      }
      d.jump = Math.max(0, d.jump - dt);
      d.x -= d.speed * dt;
      if (d.x > RUNNER_X) return;
      const item = r.track[d.index];
      const high = height(d) >= 82;
      if (high === !!item.airborne) {
        d.count += item.value;
        K.sfx.pick();
        g.burst(RUNNER_X, item.airborne ? 417 : 553, {n: 7});
      }
      d.index++;
      if (d.index === r.track.length) {
        if (d.count === r.collect) T.success(g, {x: RUNNER_X, y: GROUND - 72});
        else {
          T.hint(g);
          d.retry = 1.3;
        }
      } else {
        d.x = 1040;
        d.airborne = !!r.track[d.index].airborne;
      }
    },
    draw(g, c, d, r) {
      T.world(c, C.sky, C.earth, GROUND);
      c.beginPath();
      c.ellipse(165, 281, 76, 28, 0, Math.PI, 0);
      c.lineWidth = 9;
      c.strokeStyle = C.earth;
      c.stroke();
      T.box(c, 40, 277, 250, 80, '#F8E7C8', 24, '#C89466');
      T.box(c, 38, 272, 254, 11, '#C89466', 8);
      T.visual(c, d.count <= 24 ? {count: d.count} : d.count, 165, 315, 216, 62);
      T.line(c, {x: 40, y: GROUND + 43}, {x: 1240, y: GROUND + 43}, C.paper, 8);
      const item = r.track[d.index];
      if (item) T.token(c, item.visual ?? {count: item.value}, {x: d.x, y: item.airborne ? 417 : 553});
      const y = GROUND - height(d) - 42;
      T.circle(c, RUNNER_X, y, 42, C.accent);
      T.circle(c, RUNNER_X + 15, y - 8, 7, C.white);
      T.line(c, {x: RUNNER_X - 35, y: y + 55}, {x: RUNNER_X + 21, y: y + 55}, C.ink, 8);
    },
    player(d) { return T.area(RUNNER_X, GROUND - height(d) - 42); },
    target(d) { return T.area(d.x, d.airborne ? 417 : 553, 112, 96); }
  });

  function height(d) {
    const progress = d.jump / FLIGHT;
    return 680 * progress * (1 - progress);
  }
})(K.gameTemplates.tools);
