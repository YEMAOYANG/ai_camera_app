/* 切灯泡. Round: {options:[visual,...], matches:[indices]}
 * Swipe through matching airborne lamps. An isolated tap does not cut.
 */
(function (T) {
  const C = T.colors;
  const HIT = 48, FLOOR = 650;

  function position(d, i) {
    const t = d.time;
    const speed = 608 + 42 * d.level;
    const angle = Math.PI * Math.max(0, Math.min(1, t / (2.45 - d.level * 0.18)));
    return {x: d.centers[i] + 35 * Math.sin(angle * 2 + i), y: FLOOR - speed * Math.sin(angle) * 0.53};
  }

  function touch(a, b, p) {
    const dx = b.x - a.x, dy = b.y - a.y;
    const q = T.clamp(((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy), 0, 1);
    return Math.hypot(a.x + q * dx - p.x, a.y + q * dy - p.y) <= HIT;
  }

  T.register('slice', {
    validate(r) {
      T.options(r, 2, 5);
      T.indices(r.matches, r.options.length, 'matches');
      T.assert(r.matches.length < r.options.length, 'slice needs at least one distractor');
    },
    reset(r, level) {
      return {centers: r.options.map((_, i) => 1280 * (i + 0.5) / r.options.length), level,
        time: 0, got: new Set(), missing: new Set(), start: null, previous: null, trail: null, life: 0};
    },
    pilot(g, d, r) {
      const i = r.matches.find(i => !d.got.has(i));
      const p = position(d, i);
      if (d.start && d.previous !== d.start) {
        T.point(g, p.x, p.y, false);
      } else {
        T.point(g, p.x + (d.start ? 54 : -54), p.y, true);
      }
    },
    update(g, d, r, dt) {
      d.time += dt;
      d.life = Math.max(0, d.life - dt);
      if (!d.life) d.trail = null;
      if (d.time > 2.45 - d.level * 0.18) {
        if (!d.got.size && !d.missing.size) T.hint(g);
        d.time = 0;
        d.missing.clear();
      }
      const p = T.getInput(g).pointer;
      if (!p.down) {
        d.start = null;
        d.previous = null;
        return;
      }
      if (!d.start) {
        d.start = {x: p.x, y: p.y};
        d.previous = d.start;
        return;
      }
      if (T.distance(d.previous, p) < 24) return;
      const a = d.previous, b = {x: p.x, y: p.y};
      d.previous = b;
      d.trail = [a, b];
      d.life = 0.18;
      for (let i = 0; i < r.options.length; i++) {
        const pos = position(d, i);
        if (d.got.has(i) || d.missing.has(i) || !touch(a, b, pos)) continue;
        if (r.matches.includes(i)) {
          d.got.add(i);
          K.sfx.whoosh();
          g.burst(pos.x, pos.y);
          if (d.got.size === r.matches.length) {
            T.success(g, pos);
            return;
          }
        } else {
          d.missing.add(i);
          T.hint(g);
        }
      }
    },
    draw(g, c, d, r) {
      T.world(c, '#24454B', '#31565D', 694);
      for (let i = 0; i < d.centers.length; i++) {
        if (d.got.has(i) || d.missing.has(i)) continue;
        const {x, y} = position(d, i);
        T.box(c, x - 26, y + 19, 52, 40, '#A1BEC0', 12);
        T.token(c, r.options[i], {x, y}, 153, 92, '#FFF3D2');
      }
      if (d.trail) {
        T.line(c, d.trail[0], d.trail[1], '#E9FFE9', 13);
        T.line(c, d.trail[0], d.trail[1], '#75D4A6', 5);
      }
    },
    player(d) {
      return d.trail ? T.area(d.trail[1].x, d.trail[1].y, 96) : T.area(640, 653, 120, 89);
    },
    target(d) {
      const i = d.centers.findIndex((_, i) => !d.got.has(i) && !d.missing.has(i));
      const p = i < 0 ? null : position(d, i);
      return p ? T.area(p.x, p.y, 153, 92) : null;
    }
  });
})(K.gameTemplates.tools);
