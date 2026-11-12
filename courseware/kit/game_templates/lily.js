/* 跳荷叶. Round: {from?:visual, options:[visual,visual,(visual)], answer:index}
 * Choose a lane, then the frog jumps when the visible countdown finishes.
 */
(function (T) {
  const C = T.colors;
  const START_X = 306, END_X = 850;

  function lane(index, count) {
    return count === 2 ? [365, 570][index] : [318, 466, 614][index];
  }

  T.register('lily', {
    validate(r) {
      T.options(r, 2, 3);
      T.answer(r);
      if (r.from != null) T.validateVisual(r.from);
    },
    reset(r, level) {
      return {x: START_X, y: 472, countdown: 2.65 - level * 0.28, interval: 2.65 - level * 0.28,
        count: r.options.length, selected: -1, leap: 0, hold: 0, toY: 472};
    },
    pilot(g, d, r) {
      T.point(g, END_X, lane(r.answer, d.count), true);
    },
    update(g, d, r, dt) {
      const input = T.getInput(g);
      if (d.hold > 0) {
        d.hold = Math.max(0, d.hold - dt);
        if (!d.hold) {
          d.x = START_X;
          d.y = 472;
          d.selected = -1;
          d.countdown = d.interval;
        }
        return;
      }
      if (d.leap > 0) {
        d.leap = Math.min(1, d.leap + dt * 1.9);
        d.x = START_X + (END_X - START_X) * d.leap;
        d.y = 472 + (d.toY - 472) * d.leap - 78 * Math.sin(Math.PI * d.leap);
        if (d.leap >= 1) {
          d.leap = 0;
          if (d.selected === r.answer) T.success(g, d);
          else {
            T.hint(g);
            K.sfx.splash();
            d.hold = 1.2;
          }
        }
        return;
      }
      const vertical = T.axis(g, 'y');
      const pointer = input.taps.find(t => !t.key) || input.pointer;
      if (vertical) d.selected = vertical < 0 ? 0 : d.count - 1;
      else if (pointer.active || pointer !== input.pointer) {
        d.selected = 0;
        for (let i = 1; i < d.count; i++) {
          if (Math.abs(pointer.y - lane(i, d.count)) < Math.abs(pointer.y - lane(d.selected, d.count))) d.selected = i;
        }
      }
      if (d.selected < 0) return;
      d.countdown -= dt;
      if (d.countdown <= 0) {
        d.toY = lane(d.selected, d.count);
        d.leap = 0.001;
        K.sfx.jump();
      }
    },
    draw(g, c, d, r) {
      T.world(c, '#C4E5E8');
      for (let i = 0; i < d.count; i++) {
        const y = lane(i, d.count);
        c.save();
        c.setLineDash([12, 18]);
        T.line(c, {x: START_X + 84, y: 472}, {x: END_X - 112, y}, '#8DBEBF', 4);
        c.restore();
        T.token(c, r.options[i], {x: END_X, y}, 184, 104, i === d.selected ? '#FAE4A1' : C.paper);
      }
      T.circle(c, START_X, 472, 68, '#85BC9D');
      if (r.from != null) T.token(c, r.from, {x: START_X, y: 333}, 112, 96);
      T.circle(c, d.x, d.y, 43, C.accent);
      for (const side of [-1, 1]) {
        T.circle(c, d.x + side * 21, d.y - 29, 13, C.white);
        T.circle(c, d.x + side * 21 + 3, d.y - 29, 6, C.ink);
      }
      if (d.x === START_X && d.selected >= 0) {
        c.beginPath();
        c.arc(d.x, d.y, 56, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0, d.countdown / d.interval));
        c.strokeStyle = C.paper;
        c.lineWidth = 9;
        c.stroke();
      }
    },
    player(d) { return T.area(d.x, d.y); },
    target(d) { return T.area(END_X, lane(Math.max(d.selected, 0), d.count), 184, 104); }
  });
})(K.gameTemplates.tools);
