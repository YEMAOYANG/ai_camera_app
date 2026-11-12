/* 弹弓. Round: {lamps:count,turnOff:number} OR {lamps:[visual,...],matches:[indices]}
 * Pull from the slingshot and release. The ball can only hit the wall at the end of flight.
 * Exact-quantity mode requires the child to confirm. A second hit can re-light a lamp.
 * Lamp visual objects may specify a six-digit hex color.
 */
(function (T) {
  const C = T.colors;
  const FORK = {x: 234, y: 490}, CHECK = {x: 820, y: 643};
  const FLIGHT = 0.82, MAX_PULL = 132, GRAVITY = 455, HIT = 47, FACTOR = 12;

  function aim(pull, time) {
    return {x: FORK.x - pull.x * FACTOR * time,
      y: FORK.y - pull.y * FACTOR * time + GRAVITY * time * time / 2};
  }

  function pullAt(target) {
    return {x: (FORK.x - target.x) / (FACTOR * FLIGHT),
      y: (FORK.y - target.y + GRAVITY * FLIGHT ** 2 / 2) / (FACTOR * FLIGHT)};
  }

  function lampPositions(count) {
    const columns = Math.min(5, count), rows = Math.ceil(count / columns);
    return Array.from({length: count}, (_, i) => {
      const row = Math.floor(i / columns), inRow = Math.min(columns, count - row * columns);
      return {x: 875 + (i % columns - (inRow - 1) / 2) * 106, y: 374 + (row - (rows - 1) / 2) * 131};
    });
  }

  T.register('slingshot', {
    validate(r) {
      if (Array.isArray(r.lamps)) T.options(r, 2, 10, 'lamps');
      else T.assert(T.integer(r.lamps, 2, 10), 'need 2–10 lamps');
      const count = Array.isArray(r.lamps) ? r.lamps.length : r.lamps;
      if (r.matches != null) {
        T.assert(Array.isArray(r.lamps), 'matching lamps need visuals');
        T.indices(r.matches, count, 'matches');
        T.assert(r.matches.length < count, 'slingshot matching needs a distractor');
        T.assert(r.turnOff == null, 'choose count or matching for slingshot');
      } else {
        T.assert(T.integer(r.turnOff, 1, count - 1), 'choose a target count below the lamp supply');
      }
      for (const p of lampPositions(count)) {
        const pull = pullAt(p);
        T.assert(Math.hypot(pull.x, pull.y) < MAX_PULL - 10 && FORK.x + pull.x > 0 &&
          FORK.y + pull.y < 719, 'slingshot target is outside the reachable pull range');
      }
    },
    reset(r, level) {
      const positions = lampPositions(Array.isArray(r.lamps) ? r.lamps.length : r.lamps);
      return {positions, dark: new Set(), pulling: false, pull: {x: 0, y: 0}, time: 0,
        level, shot: null, nearest: 0};
    },
    pilot(g, d, r) {
      if (d.time) return;
      if (!r.matches && d.dark.size === r.turnOff) {
        T.point(g, CHECK.x, CHECK.y, false, true);
        return;
      }
      const candidates = r.matches || d.positions.map((_, i) => i);
      const target = d.positions[candidates.find(i => !d.dark.has(i))];
      const pull = pullAt(target);
      if (!d.pulling) T.point(g, FORK.x, FORK.y, true, true);
      else if (Math.hypot(d.pull.x, d.pull.y) < 15) T.point(g, FORK.x + pull.x, FORK.y + pull.y, true);
      else T.point(g, FORK.x + pull.x, FORK.y + pull.y, false);
    },
    update(g, d, r, dt) {
      const input = T.getInput(g);
      if (d.time > 0) {
        d.time += dt;
        if (d.time < FLIGHT) return;
        d.time = 0;
        const hit = aim(d.shot, FLIGHT);
        const i = d.positions.findIndex(p => T.distance(p, hit) <= HIT);
        if (i < 0 || (r.matches && (!r.matches.includes(i) || d.dark.has(i)))) T.hint(g);
        else {
          if (d.dark.has(i)) d.dark.delete(i);
          else d.dark.add(i);
          g.burst(hit.x, hit.y);
          K.sfx.pop();
          if (r.matches && d.dark.size === r.matches.length) T.success(g, hit);
        }
        return;
      }
      if (!r.matches && input.taps.some(p => !p.key && T.distance(p, CHECK) <= 47)) {
        if (d.dark.size === r.turnOff) T.success(g, CHECK);
        else T.hint(g);
        return;
      }
      const p = input.pointer;
      if (!d.pulling && p.down && input.taps.some(p => !p.key && T.distance(p, FORK) <= 52)) {
        d.pulling = true;
      }
      if (d.pulling && p.down) {
        const x = p.x - FORK.x, y = p.y - FORK.y;
        const scale = Math.min(1, MAX_PULL / Math.max(1, Math.hypot(x, y)));
        d.pull = {x: x * scale, y: y * scale};
        const p2 = aim(d.pull, FLIGHT);
        d.nearest = d.positions.reduce((a, b, i) => T.distance(p2, b) < T.distance(p2, d.positions[a]) ? i : a, 0);
      } else if (d.pulling) {
        d.pulling = false;
        if (Math.hypot(d.pull.x, d.pull.y) >= 15) {
          d.shot = d.pull;
          d.time = 0.001;
          K.sfx.whoosh();
        }
        d.pull = {x: 0, y: 0};
      }
    },
    draw(g, c, d, r) {
      T.world(c, '#F2EBDD', '#E7D4BD', 687);
      T.box(c, 553, 238, 636, 334, '#425D5D', 35);
      for (let i = 0; i < d.positions.length; i++) {
        const p = d.positions[i], v = Array.isArray(r.lamps) ? r.lamps[i] : null;
        const on = !d.dark.has(i), glow = v && v.color ? v.color : '#FFDD83';
        T.circle(c, p.x, p.y, 47, on ? glow : '#93AAA9');
        T.circle(c, p.x, p.y, 40, on ? '#FFFFFF44' : '#40595F');
        if (on && v != null) T.visual(c, v, p.x, p.y, 70, 68);
        if (on && v == null) T.circle(c, p.x - 14, p.y - 17, 9, '#FFFEDE');
      }
      T.line(c, {x: FORK.x - 30, y: FORK.y - 42}, {x: FORK.x, y: FORK.y + 44}, '#8D583D', 21);
      T.line(c, {x: FORK.x + 29, y: FORK.y - 42}, {x: FORK.x, y: FORK.y + 44}, '#8D583D', 21);
      T.line(c, {x: FORK.x, y: FORK.y + 44}, {x: FORK.x, y: FORK.y + 103}, '#8D583D', 21);
      const hand = {x: FORK.x + d.pull.x, y: FORK.y + d.pull.y};
      for (const dx of [-30, 29]) T.line(c, {x: FORK.x + dx, y: FORK.y - 42}, hand, '#A06E3E', 8);
      T.circle(c, hand.x, hand.y, 15, C.ink);
      if (d.pulling && Math.hypot(d.pull.x, d.pull.y) >= 15) {
        const point = aim(d.pull, FLIGHT);
        c.save();
        c.beginPath();
        c.rect(560, 242, 620, 325);
        c.clip();
        for (let i = 1; i <= 6; i++) {
          const p = aim(d.pull, i / 7 * FLIGHT);
          T.circle(c, p.x, p.y, 6, C.paper);
        }
        T.line(c, {x: point.x - 21, y: point.y}, {x: point.x + 21, y: point.y}, C.paper, 4);
        T.line(c, {x: point.x, y: point.y - 21}, {x: point.x, y: point.y + 21}, C.paper, 4);
        c.restore();
      }
      if (d.time) {
        const p = aim(d.shot, d.time);
        T.circle(c, p.x, p.y, 16, C.ink);
      }
      if (!r.matches) {
        T.circle(c, CHECK.x, CHECK.y, 47, C.accent);
        T.line(c, {x: CHECK.x - 17, y: CHECK.y}, {x: CHECK.x - 4, y: CHECK.y + 13}, C.white, 8);
        T.line(c, {x: CHECK.x - 4, y: CHECK.y + 13}, {x: CHECK.x + 18, y: CHECK.y - 12}, C.white, 8);
      }
    },
    player() { return T.area(FORK.x, FORK.y, 112); },
    target(d) { const p = d.positions[d.nearest]; return T.area(p.x, p.y, 104); }
  });
})(K.gameTemplates.tools);
