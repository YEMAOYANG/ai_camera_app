/* 开车描字 / 路径观察. Round: {strokes:[[[x,y],...],...],
 *   background?:visual, imageBox?:[centerX,centerY,width,height], mirrorImage?:true,
 *   gridBox?:[centerX,centerY,size], strokeEnds?:[visual,...],
 *   vehicle?:'lens', showRoute?:false}
 * Start at the vehicle, hold and follow in order. Coordinates are logical px.
 */
(function (T) {
  const C = T.colors;
  const CORRIDOR = 48;
  const CORNER_EPSILON = 1e-7;

  function path(points) {
    const p = points.map(([x, y]) => ({x, y}));
    const lengths = [0];
    for (let i = 1; i < p.length; i++) lengths.push(lengths[i - 1] + T.distance(p[i - 1], p[i]));
    return {points: p, lengths, length: lengths.at(-1)};
  }

  function at(p, s) {
    const i = p.lengths.findIndex(distance => distance > s);
    if (i < 0) return p.points.at(-1);
    const weight = (s - p.lengths[i - 1]) / (p.lengths[i] - p.lengths[i - 1]);
    const a = p.points[i - 1], b = p.points[i];
    return {x: a.x + (b.x - a.x) * weight, y: a.y + (b.y - a.y) * weight};
  }

  function paint(c, path, end, color, width) {
    if (end <= 0) return;
    c.beginPath();
    c.moveTo(path.points[0].x, path.points[0].y);
    for (let i = 1; i < path.points.length && path.lengths[i] < end; i++) {
      c.lineTo(path.points[i].x, path.points[i].y);
    }
    const last = at(path, end);
    c.lineTo(last.x, last.y);
    c.lineCap = c.lineJoin = 'round';
    c.strokeStyle = color;
    c.lineWidth = width;
    c.stroke();
  }

  function segmentEnd(path, s) {
    // Projection can stop just short of a vertex because of floating point rounding.
    return path.lengths.find(distance => distance - s > CORNER_EPSILON) ?? path.length;
  }

  function drive(d, pointer, path, dt) {
    const look = Math.min(segmentEnd(path, d.s), d.s + 88);
    const start = at(path, d.s), end = at(path, look);
    const dx = end.x - start.x, dy = end.y - start.y;
    const projected = ((pointer.x - start.x) * dx + (pointer.y - start.y) * dy) / (dx * dx + dy * dy);
    const choice = d.s + (look - d.s) * T.clamp(projected, 0, 1);
    if (T.distance(at(path, choice), pointer) > (d.corridor ?? CORRIDOR)) return false;
    d.s = Math.min(choice, d.s + dt * d.speed);
    const finalSegment = path.length - path.lengths.at(-2);
    const snap = Math.min(18, finalSegment * 0.3);
    if (path.length - d.s <= snap && T.distance(pointer, path.points.at(-1)) <= snap) d.s = path.length;
    return true;
  }

  function keyboardCursor(g, d, path) {
    const input = T.getInput(g);
    if (!g.score || g.auto) return input.pointer;
    if (input.taps.some(tap => tap.key)) d.keyboard = !d.keyboard;
    if (!d.keyboard) return input.pointer;
    const here = at(path, d.s);
    const ahead = at(path, Math.min(segmentEnd(path, d.s), d.s + 42));
    if (!d.grip || d.release) return {...here, down: true};
    const x = T.axis(g, 'x'), y = T.axis(g, 'y');
    const alignment = (ahead.x - here.x) * x + (ahead.y - here.y) * y;
    const advancing = alignment > .33 * T.distance(here, ahead) * Math.hypot(x, y);
    if ((x || y) && !advancing) T.hint(g);
    const point = advancing ? ahead : here;
    return {x:point.x+d.grip.x, y:point.y+d.grip.y, down:true};
  }

  T.register('trace', {
    controls: [['left','←','小车向左'], ['right','→','小车向右'],
      ['up','↑','小车向上'], ['down','↓','小车向下'], ['action','◎','拿起或放下小车']],
    validate(r) {
      T.assert(Array.isArray(r.strokes) && T.integer(r.strokes.length, 1, 8), 'trace needs 1–8 strokes');
      T.assert(r.prefill == null || (Array.isArray(r.prefill) && r.prefill.length <= 7), 'invalid completed strokes');
      T.assert(r.corridor == null || T.integer(r.corridor, 32, 66), 'invalid trace corridor');
      for (const points of [...r.strokes, ...(r.prefill || [])]) {
        T.assert(Array.isArray(points) && points.length >= 2 && points.length <= 300 &&
          points.every(p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) &&
            p[0] >= 160 && p[0] <= 1120 && p[1] >= 220 && p[1] <= 640), 'trace points are outside the drawing area');
        const stroke = path(points);
        T.assert(stroke.length >= 24 && stroke.length <= 2500 &&
          stroke.lengths.slice(1).every((n, i) => n > stroke.lengths[i]), 'invalid trace stroke length');
      }
      if (r.background != null) T.validateVisual(r.background);
      if (r.car != null) T.validateVisual(r.car);
      if (r.imageBox != null) {
        T.assert(Array.isArray(r.imageBox), 'invalid trace image box');
        const [x, y, w, h] = r.imageBox;
        T.assert(r.imageBox.length === 4 && r.imageBox.every(Number.isFinite) && w >= 88 && h >= 88 &&
          x - w / 2 >= 40 && x + w / 2 <= 1240 && y - h / 2 >= 222 && y + h / 2 <= 698, 'invalid trace image box');
      }
      if (r.gridBox != null) {
        T.assert(Array.isArray(r.gridBox) && r.gridBox.length === 3 && r.gridBox.every(Number.isFinite), 'invalid trace grid box');
        const [x, y, size] = r.gridBox;
        T.assert(size >= 88 && x - size / 2 >= 85 && x + size / 2 <= 1195 &&
          y - size / 2 >= 221 && y + size / 2 <= 698, 'trace grid is outside the drawing area');
      }
      if (r.strokeEnds != null) {
        T.assert(Array.isArray(r.strokeEnds) && r.strokeEnds.length === r.strokes.length, 'trace needs an end visual per stroke');
        r.strokeEnds.forEach(T.validateVisual);
      }
      T.assert(r.vehicle == null || r.vehicle === 'lens', 'trace vehicle must be lens or omitted');
    },
    reset(r, level) {
      return {paths: r.strokes.map(path), stroke: 0, s: 0, grip: null, release: false,
        speed: 300 + 30 * level, background: r.background, prefill: (r.prefill || []).map(path),
        corridor: r.corridor, keyboard: false};
    },
    pilot(g, d) {
      const p = d.paths[d.stroke];
      const position = at(p, d.release || !d.grip ? d.s : Math.min(segmentEnd(p, d.s), d.s + 42));
      T.point(g, position.x, position.y, !d.release);
    },
    update(g, d, r, dt) {
      const p = d.paths[d.stroke];
      const cursor = keyboardCursor(g, d, p);
      if (!cursor.down) {
        d.grip = null;
        d.release = false;
        return;
      }
      if (d.release) return;
      if (!d.grip) {
        const here = at(p, d.s);
        if (T.distance(cursor, here) > 52) return;
        d.grip = {x: cursor.x - here.x, y: cursor.y - here.y};
        return;
      }
      if (!drive(d, {x: cursor.x - d.grip.x, y: cursor.y - d.grip.y}, p, dt)) {
        T.hint(g);
        d.grip = null;
        return;
      }
      if (d.s < p.length - 0.001) return;
      if (d.stroke === d.paths.length - 1) {
        T.success(g, p.points.at(-1));
      } else {
        g.sparkle(p.points.at(-1).x, p.points.at(-1).y);
        K.sfx.pick();
        if (g.demoAction?.()) return;
        g.awardPoint?.();
        d.stroke++;
        d.s = 0;
        d.release = !d.keyboard;
        if (d.keyboard) d.grip = null;
        d.keyboard = false;
      }
    },
    draw(g, c, d, r) {
      T.world(c, '#E9F3F0');
      T.box(c, 85, 221, 1110, 477, C.paper, 30, C.line);
      if (d.background != null) {
        const box = r.imageBox || [640, 460, 1080, 450];
        c.save();
        if (r.mirrorImage) {
          c.translate(box[0] * 2, 0);
          c.scale(-1, 1);
        }
        T.visual(c, d.background, ...box);
        c.restore();
      }
      if (r.gridBox) {
        const [x, y, size] = r.gridBox, edge = size / 2;
        T.box(c, x - edge, y - edge, size, size, '#FFFFFF11', 0, '#729E92');
        c.save();
        c.setLineDash([11, 13]);
        T.line(c, {x: x - edge, y}, {x: x + edge, y}, '#92B8AC', 3);
        T.line(c, {x, y: y - edge}, {x, y: y + edge}, '#92B8AC', 3);
        c.restore();
      }
      for (const done of d.prefill) paint(c, done, done.length, '#6D9F94', 12);
      for (let i = 0; i < d.paths.length; i++) {
        const p = d.paths[i];
        if (r.showRoute !== false && (!g.score || i === d.stroke)) {
          c.save();
          if (r.vehicle === 'lens') c.setLineDash([8, 12]);
          paint(c, p, p.length, r.vehicle === 'lens' ? '#64AD9FA8' : '#BCD7CC', r.vehicle === 'lens' ? 6 : 27);
          c.restore();
          if (r.vehicle !== 'lens') T.circle(c, p.points.at(-1).x, p.points.at(-1).y, 13, '#61A38F');
        }
        paint(c, p, i < d.stroke ? p.length : i === d.stroke ? d.s : 0,
          r.vehicle === 'lens' ? '#127B7699' : C.accent, r.vehicle === 'lens' ? 6 : 12);
        if (r.strokeEnds && (i < d.stroke || (i === d.stroke && g.data.next))) {
          const end = p.points.at(-1);
          T.visual(c, r.strokeEnds[i], end.x, end.y - 46, 100, 52);
        }
      }
      const {x, y} = at(d.paths[d.stroke], d.s);
      if (r.vehicle === 'lens') {
        T.line(c, {x: x + 25, y: y + 26}, {x: x + 51, y: y + 53}, C.ink, 13);
        c.beginPath();
        c.arc(x, y, 36, 0, Math.PI * 2);
        c.fillStyle = '#DDF9EE66';
        c.fill();
        c.strokeStyle = C.accent;
        c.lineWidth = 9;
        c.stroke();
      } else if (r.car) {
        T.visual(c, r.car, x, y, 100, 74);
      } else {
        T.box(c, x - 42, y - 28, 84, 56, '#E79C5E', 20, C.ink);
        T.box(c, x - 14, y - 24, 32, 48, C.sky, 10);
        for (const dx of [-24, 24]) {
          for (const dy of [-27, 27]) T.box(c, x + dx - 12, y + dy - 7, 24, 14, C.ink, 5);
        }
      }
    },
    player(d) { const p = at(d.paths[d.stroke], d.s); return T.area(p.x, p.y, 108); },
    target(d) { const p = d.paths[d.stroke].points.at(-1); return T.area(p.x, p.y, 96); }
  });
})(K.gameTemplates.tools);
