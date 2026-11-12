// Slide every piece in one direction, as in 2048. A contact merges only
// when the level supplies [piece, partner, result]. Results go to the shelf.
K.gameTemplates.slideMerge = config => {
  const {box, center, create, bot, sprite, token, validToken} = Classic;
  const directions = ['left', 'right', 'up', 'down'];
  const size = 4;
  const cell = 104;
  const models = new Map();
  const at = index => [362 + (index % size) * cell, 172 + Math.floor(index / size) * cell];
  const shelf = index => [872 + (index % 2) * 120, 230 + Math.floor(index / 2) * 94];

  function lanes(walls, direction) {
    const segments = [];
    for (let line = 0; line < size; line++) {
      let segment = [];
      for (let step = 0; step < size; step++) {
        const offset = direction === 'right' || direction === 'down' ? size - 1 - step : step;
        const index = direction === 'up' || direction === 'down' ? offset * size + line : line * size + offset;
        if (walls.has(index)) {
          if (segment.length) segments.push(segment);
          segment = [];
        } else {
          segment.push(index);
        }
      }
      if (segment.length) segments.push(segment);
    }
    return segments;
  }

  function slide(model, board, remaining, direction, animate = false) {
    const next = Array(size * size).fill(null);
    const slots = remaining.slice();
    const results = [];
    const motions = [];
    let changed = false;
    for (const segment of model.lanes.get(direction)) {
      const pieces = segment.filter(index => board[index] !== null);
      for (let i = 0, slot = 0; i < pieces.length; i++, slot++) {
        const from = pieces[i];
        const to = segment[slot];
        const partner = pieces[i + 1];
        const result = model.pairs.get(board[from])?.get(board[partner]);
        if (animate) motions.push({from, to, value: board[from]});
        const target = slots.indexOf(result);
        if (target !== -1) {
          if (animate) motions.push({from: partner, to, value: board[partner]});
          results.push(target);
          slots[target] = null;
          i++;
          changed = true;
        } else {
          next[to] = board[from];
          changed ||= from !== to;
        }
      }
    }
    return changed ? {board: next, remaining: slots, results, motions} : null;
  }

  function solve(model, board, remaining) {
    const key = (board, slots) => JSON.stringify([board, slots]);
    const queue = [{board, remaining, first: null}];
    const seen = new Set([key(board, remaining)]);
    for (let i = 0; i < queue.length && i < 5000; i++) {
      const current = queue[i];
      for (const direction of directions) {
        const next = slide(model, current.board, current.remaining, direction);
        if (!next) continue;
        const first = current.first || direction;
        if (next.board.every(value => value === null)) return first;
        const nextKey = key(next.board, next.remaining);
        if (seen.has(nextKey)) continue;
        seen.add(nextKey);
        queue.push({board: next.board, remaining: next.remaining, first});
      }
    }
    return null;
  }

  function validate(level, index) {
    const {board, walls = [], pairs, targets, seconds} = level;
    if (!Array.isArray(board) || board.length !== size || board.some(row =>
      !Array.isArray(row) || row.length !== size || Array.from(row).some(value => value !== null && !validToken(value)))) {
      throw new Error('slide merge requires a 4 by 4 board');
    }
    const flat = board.flat();
    const count = flat.filter(value => value !== null).length;
    if (count < 2 || count > 8 || count % 2 || !Array.isArray(walls) || new Set(walls).size !== walls.length ||
      Array.from(walls).some(i => !Number.isInteger(i) || i < 0 || i >= flat.length || flat[i] !== null) ||
      !Array.isArray(pairs) || !pairs.length || pairs.length > 16 || !Array.isArray(targets) ||
      targets.length !== count / 2 || !Array.from(targets).every(validToken) || !(seconds >= .15 && seconds <= .4)) {
      throw new Error('invalid slide merge level');
    }
    const model = {flat, targets: [...targets], walls: new Set(walls), pairs: new Map(), lanes: new Map()};
    for (const triple of pairs) {
      if (!Array.isArray(triple) || triple.length !== 3 || !Array.from(triple).every(validToken)) {
        throw new Error('slide merge rules must be [piece, partner, result]');
      }
      const [a, b, result] = triple;
      if (model.pairs.get(a)?.has(b)) throw new Error('ambiguous slide merge rule');
      if (!model.pairs.has(a)) model.pairs.set(a, new Map());
      if (!model.pairs.has(b)) model.pairs.set(b, new Map());
      model.pairs.get(a).set(b, result);
      model.pairs.get(b).set(a, result);
    }
    for (const direction of directions) model.lanes.set(direction, lanes(model.walls, direction));
    model.first = solve(model, flat, model.targets);
    if (!model.first) throw new Error(`slide merge level ${index + 1} has no complete route`);
    models.set(level, model);
  }

  function reset(level) {
    const model = models.get(level);
    return {board: model.flat, remaining: model.targets, model, animation: null, cooldown: 0,
      startedAt: 0, help: false, suggestion: model.first};
  }

  function update(world, level, input, dt, feedback) {
    world.cooldown = Math.max(0, world.cooldown - dt);
    if (input.press('action')) {
      const help = world.help;
      Object.assign(world, reset(level), {help});
      feedback.resetCheckpoint();
      feedback.move();
      feedback.fx(518, 328);
      return;
    }
    if (world.cooldown > 0) return;
    const direction = directions.find(key => input.press(key));
    if (!direction) return;
    const move = slide(world.model, world.board, world.remaining, direction, true);
    world.cooldown = level.seconds;
    if (!move) {
      feedback.lost(518, 328);
      return;
    }
    world.board = move.board;
    world.remaining = move.remaining;
    world.suggestion = null;
    world.startedAt = null;
    world.animation = move;
    feedback.move();
    if (!move.results.length) feedback.fx(...at(move.motions[0].to));
    if (world.help && world.remaining.some(value => value !== null)) {
      world.suggestion = solve(world.model, world.board, world.remaining);
    }
    for (const slot of move.results) feedback.award(...shelf(slot));
  }

  function drawValue(context, images, value, x, y, width, height, labels, color = '#253b33') {
    const label = labels?.[value];
    const accented = typeof label === 'string' && /^(.*?)([A-Za-zɑ])([\u0300\u0301\u0304\u030c])(.*)$/u.exec(label);
    if (!accented || images.icons.has(String(value))) {
      token(context, images, value, x, y, width, height, labels, color);
      return;
    }
    // Position an explicit combining mark over its base letter, even when a
    // system's fallback font has no placement anchor for that combination.
    const [, prefix, letter, mark, suffix] = accented;
    const base = prefix + letter + suffix;
    const fontSize = Math.min(height * .63, width / (Array.from(base).length * .65));
    context.save();
    Classic.text(context, base, x, y + 5, fontSize, color);
    const center = x - context.measureText(base).width / 2 + context.measureText(prefix).width +
      context.measureText(letter).width / 2;
    const top = y + 5 - fontSize * .49;
    const half = fontSize * .13;
    const offsets = { '\u0300': [-.55, .55], '\u0301': [.55, -.55], '\u0304': [0, 0], '\u030c': [-.46, .46, -.46] }[mark];
    context.strokeStyle = color;
    context.lineWidth = Math.max(2, fontSize * .055);
    context.lineCap = 'round';
    context.beginPath();
    offsets.forEach((offset, i) => {
      const dx = center - half + 2 * half * i / (offsets.length - 1);
      const dy = top + offset * half;
      if (i === 0) context.moveTo(dx, dy);
      else context.lineTo(dx, dy);
    });
    context.stroke();
    context.restore();
  }

  function draw(world, level, context, images, game) {
    box(context, 294, 103, 449, 450, 27, '#203c35');
    box(context, 798, 132, 270, 343, 24, '#365b4c');
    for (let index = 0; index < size * size; index++) {
      const [x, y] = at(index);
      box(context, x - 48, y - 48, 96, 96, 13, world.model.walls.has(index) ? '#698575' : '#42665a');
    }
    function drawTile(value, x, y, merged) {
      box(context, x - 44, y - 40, 88, 80, 14, merged ? '#eebd67' : '#fff0d2');
      drawValue(context, images, value, x, y, 79, 68, level.labels);
    }
    if (world.startedAt === null) world.startedAt = game.t;
    const fraction = world.animation ? Math.min(1, (game.t - world.startedAt) / (level.seconds * .8)) : 1;
    const hop = fraction < 1 && world.animation.results.length > 0;
    sprite(context, images.frames[hop ? 1 : 0] || images.frames[0], 195,
      412 - (hop ? 24 * Math.sin(fraction * Math.PI) : 0), 132, 129);
    if (fraction < 1) {
      const distance = 1 - (1 - fraction) ** 3;
      for (const {from, to, value} of world.animation.motions) {
        const [x, y] = at(from);
        const [tx, ty] = at(to);
        drawTile(value, x + (tx - x) * distance, y + (ty - y) * distance, false);
      }
    } else {
      world.board.forEach((value, i) => { if (value !== null) drawTile(value, ...at(i), false); });
    }
    world.model.targets.forEach((value, i) => {
      const [x, y] = shelf(i);
      const pending = world.remaining[i] !== null || (fraction < 1 && world.animation.results.includes(i));
      if (pending) {
        box(context, x - 46, y - 34, 92, 68, 13, '#547b65');
        drawValue(context, images, value, x, y, 73, 59, level.labels, '#e5efd7');
      } else {
        drawTile(value, x, y, true);
      }
    });
    if (world.help && world.suggestion) {
      const arrows = {left: '←', right: '→', up: '↑', down: '↓'};
      box(context, 475, 557, 86, 46, 16, '#f4c66f');
      Classic.text(context, arrows[world.suggestion], 518, 578, 40);
    }
  }

  return create(config, {
    controls: [...directions, ['action', '↶', '这一关重来']], backdrop: '#294f40',
    validate, reset, update, draw,
    goal: level => models.get(level).targets.length,
    adapt(world, misses) {
      world.help = misses >= 2;
      if (world.help) world.suggestion = solve(world.model, world.board, world.remaining);
    },
    player: () => center(519, 328, 435, 435),
    target: () => center(933, 307, 264, 340),
    pilot(world) {
      if (world.cooldown > 0) return bot();
      return bot(world.suggestion || solve(world.model, world.board, world.remaining) || 'action');
    },
  });
};
